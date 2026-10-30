"""Read-only BeoCore mDNS browser. No advertising or TV control connection."""
import argparse
import json
import threading
import time

SERVICE = "_beocore._tcp.local."


def describe(info):
    def text(value):
        return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value

    properties = {text(key): text(value) for key, value in info.properties.items()}
    return {"instance": info.name, "name": properties.get("name", ""),
            "addresses": info.parsed_addresses(), "jid": properties.get("jid", ""),
            "port": info.port}


class Listener:
    def __init__(self):
        self.records = {}
        self.lock = threading.Lock()

    def add_service(self, zeroconf, service_type, name):
        info = zeroconf.get_service_info(service_type, name, timeout=1000)
        if info is not None:
            with self.lock:
                self.records[name] = describe(info)

    update_service = add_service

    def remove_service(self, _zeroconf, _service_type, name):
        with self.lock:
            self.records.pop(name, None)


def browse(timeout):
    from zeroconf import IPVersion, ServiceBrowser, Zeroconf

    listener = Listener()
    with Zeroconf(ip_version=IPVersion.V4Only) as zeroconf:
        browser = ServiceBrowser(zeroconf, SERVICE, listener)
        try:
            time.sleep(timeout)
        finally:
            browser.cancel()
    with listener.lock:
        return sorted(listener.records.values(), key=lambda item: item["instance"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=10,
                        help="Browse for 1–60 seconds (default 10)")
    args = parser.parse_args()
    if not 1 <= args.timeout <= 60:
        parser.error("--timeout must be between 1 and 60 seconds")
    try:
        records = browse(args.timeout)
    except (ImportError, OSError) as error:
        parser.exit(1, f"Discovery unavailable: {error}\nInstall the runtime requirements and check LAN access.\n")
    print(json.dumps(records, indent=2, ensure_ascii=False))
    if not records:
        parser.exit(1, "No BeoCore services found. Check the LAN and wake the TV normally.\n")


if __name__ == "__main__":
    main()
