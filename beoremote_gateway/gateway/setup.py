"""Persist an explicitly selected product; discover its current LAN addresses."""
import asyncio
from dataclasses import replace
import json
import logging
import os
from pathlib import Path
import time
import tempfile

from .autodetect import PRODUCT_JID, discover_devices, route_address
from .actions import ActionManager, rule_id
from .config import Options
from .learning import ButtonLearning
from .runtime import GatewayRuntime
from .sources import SourceSettings
from .tv_sources import TVSources

LOG = logging.getLogger(__name__)
SETUP_PATH = Path("/data/selected-tv.json")


def read_selection(path):
    if not path.exists():
        return None
    if path.stat().st_size > 4096:
        raise ValueError("Saved TV selection is too large")
    data = json.loads(path.read_text())
    if (not isinstance(data, dict) or set(data) != {"jid", "name", "enabled"}
            or not isinstance(data["jid"], str) or not PRODUCT_JID.fullmatch(data["jid"])
            or not isinstance(data["name"], str) or len(data["name"]) > 128
            or type(data["enabled"]) is not bool):
        raise ValueError("Saved TV selection is invalid; choose your TV again")
    return data


def save_selection(path, selection):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent,
                                         prefix="." + path.name + "-", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(selection, stream)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)



class SetupController:
    def __init__(self, options, path=SETUP_PATH, scanner=discover_devices,
                 route=route_address, runtime_factory=GatewayRuntime, actions=None):
        self.options, self.path = options, Path(path)
        self.scanner, self.route, self.runtime_factory = scanner, route, runtime_factory
        self.selection = self.runtime = self.worker = None
        self.sources = SourceSettings(self.path.parent)
        self.learning, self.actions = ButtonLearning(), actions or ActionManager()
        self.devices = []
        self.scanned_at = float("-inf")
        self.error = ""
        self.state = "choose_tv" if options.mode == "auto" else options.mode
        self.scan_lock, self.lock = asyncio.Lock(), asyncio.Lock()
        self.wake, self.stop = asyncio.Event(), asyncio.Event()

    async def start(self):
        if self.options.mode == "auto":
            try:
                self.selection = read_selection(self.path)
                if self.selection is not None:
                    self.state = "waiting" if self.selection["enabled"] else "paused"
            except (OSError, ValueError) as error:
                self.error = str(error)
            self.worker = asyncio.create_task(self.maintain(), name="tv-discovery")
        elif self.options.mode != "disabled":
            self.runtime = self.runtime_factory(self.options)
            self.runtime.observer = self.learning.observe
            await self.runtime.start()
            self.state = "active"

    async def scan(self):
        async with self.scan_lock:
            if time.monotonic() - self.scanned_at >= 5:
                self.devices = await self.scanner(excluded_jid=self.options.gateway_jid)
                self.scanned_at = time.monotonic()
            return self.devices

    async def select(self, jid):
        if self.options.mode != "auto":
            raise ValueError("Set Mode to auto in the app's Configuration tab and restart first.")
        if not any(item["jid"] == jid for item in self.devices):
            raise ValueError("Search again, then choose a product from the list.")
        if time.monotonic() - self.scanned_at > 60:
            await self.scan()
        async with self.lock:
            record = next((item for item in self.devices if item["jid"] == jid), None)
            if record is None:
                raise ValueError("Search again, then choose a product from the list.")
            selection = {"jid": record["jid"], "name": record["name"], "enabled": True}
            save_selection(self.path, selection)
            if self.selection is not None and self.selection["jid"] != jid:
                await self.sources.close()
            self.selection = selection
            await self._apply(record)
            self.wake.set()

    async def pause(self):
        if self.options.mode != "auto":
            raise ValueError("Manual mode is controlled in the app's Configuration tab.")
        async with self.lock:
            if self.selection is not None:
                selection = {**self.selection, "enabled": False}
                save_selection(self.path, selection)
                self.selection = selection
            await self._close_runtime()
            self.state, self.error = "paused", ""
            self.wake.set()

    async def resume(self):
        if self.options.mode != "auto":
            raise ValueError("Manual mode is controlled in the app's Configuration tab.")
        async with self.lock:
            if self.selection is None:
                raise ValueError("Choose your TV first.")
            selection = {**self.selection, "enabled": True}
            save_selection(self.path, selection)
            self.selection = selection
            self.state, self.error = "waiting", ""
            self.wake.set()
        await self.reconcile()

    async def _close_runtime(self):
        self.learning.finish()
        if self.runtime is not None:
            runtime, self.runtime = self.runtime, None
            await runtime.close()

    async def _apply(self, record):
        try:
            remote, local = self.route(record["addresses"])
            options = replace(self.options, mode="advertise", horizon_address=remote,
                              horizon_jid=record["jid"], advertise_address=local,
                              publish_ha_events=True)
            options = Options.from_dict(options.as_dict())
            if (self.runtime is None or self.runtime.options != options
                    or not self.runtime.snapshot()["healthy"]):
                await self._close_runtime()
                runtime = self.runtime_factory(options)
                runtime.observer = self.learning.observe
                await runtime.start()
                self.runtime = runtime
            self.state, self.error = "active", ""
        except (OSError, ValueError, RuntimeError) as error:
            await self._close_runtime()
            self.state, self.error = "error", str(error)
            LOG.warning("tv_setup_failed reason=%s", type(error).__name__)

    async def reconcile(self):
        # Never pick another product automatically, even if only one is visible.
        selected = self.selection
        if selected is None or not selected["enabled"]:
            return
        devices = await self.scan()
        async with self.lock:
            if self.selection != selected:
                return
            record = next((item for item in devices if item["jid"] == selected["jid"]), None)
            if record is not None:
                await self._apply(record)
            elif self.runtime is None:
                self.state, self.error = "waiting", "Wake your selected TV or check the network."

    async def maintain(self):
        while not self.stop.is_set():
            self.wake.clear()
            try:
                await self.reconcile()
            except (OSError, ValueError, RuntimeError) as error:
                self.error = "Discovery is unavailable. Check the local network and search again."
                LOG.warning("tv_discovery_retry reason=%s", type(error).__name__)
            try:
                await asyncio.wait_for(self.wake.wait(), timeout=30)
            except asyncio.TimeoutError:
                pass

    def snapshot(self):
        runtime = self.runtime.snapshot() if self.runtime else {
            "healthy": True, "listener": False, "discovery": False, "peers": 0,
            "received": 0, "suppressed": 0, "ha": {"delivery": "disabled"}}
        return {**runtime, "healthy": runtime["healthy"] and (self.worker is None or not self.worker.done()),
                "mode": self.options.mode, "setup": self.state}

    def status(self):
        result = {"mode": self.options.mode, "state": self.state, "error": self.error,
                  "selection": self.selection, "gateway_name": self.options.gateway_name,
                  "runtime": self.snapshot(), "learning": self.learning.status(),
                  "sources": self.sources.status()}
        if result["learning"]["state"] == "captured":
            event = self.learning.capture(result["learning"]["id"], self.action_tv())
            result["learning"]["button_id"] = rule_id(event)
        if self.runtime is not None:
            result["addresses"] = {"tv": self.runtime.options.horizon_address,
                                   "gateway": self.runtime.options.advertise_address}
            result["tv_jid"] = self.runtime.options.horizon_jid
        elif self.selection is not None:
            result["tv_jid"] = self.selection["jid"]
        return result

    def action_tv(self):
        if (self.runtime is None or not self.runtime.options.publish_ha_events
                or not self.runtime.snapshot()["listener"]):
            raise ValueError("Connect your TV first. In manual mode, also enable Publish HA events.")
        return self.runtime.options.horizon_jid

    async def set_sources_enabled(self, enabled):
        async with self.lock:
            await self.sources.set_enabled(enabled)
        return self.sources.status()

    def source_editor(self):
        if not hasattr(self, "_source_editor"):
            self._source_editor = TVSources(self.path.parent, self.actions)
        return self._source_editor

    async def _source_target(self):
        if not self.sources.enabled:
            raise ValueError("Enable source management before connecting with ADB.")
        if self.options.mode == "auto":
            if self.selection is None:
                raise ValueError("Choose your TV first.")
            jid = self.selection["jid"]
            # A TV may answer its native API while missing from a fresh mDNS
            # browse. Reuse the receiver's address only after checking its
            # product identity; never contact ADB on an unverified old IP.
            address = None
            if self.runtime is not None and self.runtime.options.horizon_jid == jid:
                candidate = self.runtime.options.horizon_address
                if await self.sources.verify(candidate, jid):
                    address = candidate
            if address is None:
                devices = await self.scan()
                record = next((item for item in devices if item["jid"] == jid), None)
                if record is None:
                    raise ValueError("Wake your selected TV and search again. No other device will be used.")
                candidate, _local = self.route(record["addresses"])
                if not await self.sources.verify(candidate, jid):
                    raise ValueError("The TV identity could not be confirmed. Wake your TV and try again.")
                address = candidate
        elif self.options.mode in ("listen", "advertise"):
            address = self.options.horizon_address
            jid = self.options.horizon_jid
            if not await self.sources.verify(address, jid):
                raise ValueError("The TV identity could not be confirmed. Wake your TV and try again.")
        else:
            raise ValueError("Choose your TV in automatic mode first.")
        local = self.runtime.options.advertise_address if self.runtime is not None else ""
        if not local:
            _remote, local = self.route([address])
        return address, jid, local

    async def inspect_sources(self):
        if self.sources.lock.locked():
            raise ValueError("A TV operation is already running. Wait for it to finish.")
        async with self.sources.lock, self.lock:
            address, jid, _local = await self._source_target()
            result = await self.sources.adb.inspect(address)
            if result.get("state") == "connected" and result.get("helper_installed"):
                result["helper"] = await self.source_editor().status(self.sources.adb, address, jid)
            return {**result, "tv_jid": jid}

    async def source_operation(self, operation, data):
        if self.sources.lock.locked():
            raise ValueError("A TV operation is already running. Wait for it to finish.")
        async with self.sources.lock, self.lock:
            address, jid, local = await self._source_target()
            if data.get("tv_jid") != jid:
                raise ValueError("The selected TV changed. Refresh the page before changing sources.")
            editor, adb = self.source_editor(), self.sources.adb
            if operation == "install":
                if not jid.startswith("7980."):
                    raise ValueError("TV source setup currently supports Beovision Horizon only.")
                inventory = await adb.inspect(address)
                if inventory.get("state") != "connected":
                    raise ValueError("Allow network debugging on the TV, then connect again.")
                if not str(inventory.get("android", "")).startswith("5.1"):
                    raise ValueError("This TV firmware has not been validated for source setup.")
                if inventory.get("helper_installed"):
                    await adb.stop_helper(address)
                await adb.install_helper(address)
                await adb.start_helper(address)
                status = await editor.wait_ready(adb, address, jid)
                if data["retire_old"]:
                    if not status.get("legacy_trusted"):
                        raise ValueError("The old helper could not be verified. It has been kept.")
                    await adb.retire_legacy(address)
                    for _ in range(15):
                        status = await editor.status(adb, address, jid)
                        if status.get("legacy_sources") == 0:
                            await adb.stop_legacy(address)
                            break
                        await asyncio.sleep(.5)
                    else:
                        raise ValueError("Choose a normal TV input before replacing the old shortcuts, then try again.")
                return await editor.status(adb, address, jid)
            if operation == "targets":
                return await self.actions.targets()
            if operation == "refresh":
                return await editor.refresh(adb, address, jid)
            if operation == "save":
                return await editor.save(adb, address, local, jid, data["revision"], data["entry"])
            if operation == "remove":
                return await editor.remove(adb, address, jid, data["revision"], data["id"])
            if operation == "restore":
                return await editor.restore(adb, address, jid, data["revision"])
            if operation == "test":
                return await editor.test(adb, address, jid, data["id"])
            raise ValueError("Unknown TV source operation.")

    async def start_learning(self):
        async with self.lock:
            return self.learning.start(self.action_tv())

    async def cancel_learning(self):
        async with self.lock:
            self.learning.finish()

    async def save_action(self, session_id, name, kind, target):
        async with self.lock:
            event = self.learning.capture(session_id, self.action_tv())
            result = await self.actions.save(event, name, kind, target)
            self.learning.finish()
            return result

    async def toggle_action(self, key, enabled):
        async with self.lock:
            await self.actions.toggle(key, self.action_tv(), enabled)

    async def update_action(self, key, name, kind, target):
        async with self.lock:
            return await self.actions.update(key, self.action_tv(), name, kind, target)

    async def remove_action(self, key):
        async with self.lock:
            await self.actions.remove(key, self.action_tv())

    async def close(self):
        self.stop.set()
        if self.worker is not None:
            self.worker.cancel()
            await asyncio.gather(self.worker, return_exceptions=True)
        async with self.lock:
            try:
                await self._close_runtime()
            finally:
                await self.sources.close()
