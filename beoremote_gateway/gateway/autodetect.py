"""Find BeoCore products through mDNS; never advertise or control a TV."""
import asyncio
import ipaddress
import re
import socket

from .config import validate_jid

SERVICE = "_beocore._tcp.local."
PRODUCT_JID = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+@products\.bang-olufsen\.com")


def device_record(info, excluded_jid=""):
    def text(value):
        return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value

    properties = {text(key): text(value) for key, value in info.properties.items()}
    jid = properties.get("jid", "")
    if (not isinstance(jid, str) or not PRODUCT_JID.fullmatch(jid)
            or jid == excluded_jid or properties.get("node") != "beocore"):
        return None
    validate_jid(jid)
    addresses = []
    for value in info.parsed_addresses():
        try:
            address = ipaddress.IPv4Address(value)
        except ValueError:
            continue
        if not (address.is_loopback or address.is_multicast or address.is_unspecified
                or str(address) == "255.255.255.255"):
            addresses.append(str(address))
    if not addresses:
        return None
    name = properties.get("name") or "B&O product"
    name = "".join(char for char in str(name) if ord(char) >= 32)[:128]
    return {"jid": jid, "name": name, "addresses": sorted(set(addresses))}


async def discover_devices(excluded_jid="", duration=3):
    from zeroconf import IPVersion, ServiceStateChange
    from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

    found, tasks, pending = {}, set(), set()
    zeroconf = AsyncZeroconf(ip_version=IPVersion.V4Only)

    async def resolve(name):
        try:
            info = AsyncServiceInfo(SERVICE, name)
            if await info.async_request(zeroconf.zeroconf, 1000):
                record = device_record(info, excluded_jid)
                if record is not None:
                    found[name] = record
        except (OSError, ValueError):
            pass
        finally:
            pending.discard(name)

    def changed(zeroconf, service_type, name, state_change):
        if state_change == ServiceStateChange.Removed:
            found.pop(name, None)
        elif name not in pending and len(pending) < 16 and len(found) < 128:
            pending.add(name)
            task = asyncio.create_task(resolve(name))
            tasks.add(task)
            task.add_done_callback(tasks.discard)

    browser = None
    try:
        browser = AsyncServiceBrowser(zeroconf.zeroconf, SERVICE, handlers=[changed])
        await asyncio.sleep(duration)
        if tasks:
            await asyncio.wait(list(tasks), timeout=1.1)
    finally:
        if browser is not None:
            await browser.async_cancel()
        for task in list(tasks):
            task.cancel()
        await asyncio.gather(*list(tasks), return_exceptions=True)
        await zeroconf.async_close()
    # One product can be visible through more than one service record/interface.
    products = {}
    for record in found.values():
        existing = products.setdefault(record["jid"], {**record, "addresses": []})
        existing["addresses"] = sorted(set(existing["addresses"] + record["addresses"]))
    return sorted(products.values(), key=lambda item: (item["name"].casefold(), item["jid"]))


def route_address(addresses):
    """Ask the local routing table for the outgoing LAN IP; sends no UDP data."""
    for remote in addresses:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            try:
                connection.connect((remote, 9))
                local = connection.getsockname()[0]
            except OSError:
                continue
        if local != remote and not ipaddress.IPv4Address(local).is_loopback:
            return remote, local
    raise OSError("No local IPv4 route to this TV. Check that it is on the same LAN.")
