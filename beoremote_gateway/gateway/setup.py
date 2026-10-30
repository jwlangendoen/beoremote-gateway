"""Persist an explicitly selected product; discover its current LAN addresses."""
import asyncio
from dataclasses import replace
import json
import logging
import os
from pathlib import Path
import time

from .autodetect import PRODUCT_JID, discover_devices, route_address
from .actions import ActionManager
from .config import Options
from .learning import ButtonLearning
from .runtime import GatewayRuntime

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
    temporary = path.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(selection, stream)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


class SetupController:
    def __init__(self, options, path=SETUP_PATH, scanner=discover_devices,
                 route=route_address, runtime_factory=GatewayRuntime, actions=None):
        self.options, self.path = options, Path(path)
        self.scanner, self.route, self.runtime_factory = scanner, route, runtime_factory
        self.selection = self.runtime = self.worker = None
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
            if self.runtime is None or self.runtime.options != options:
                await self._close_runtime()
                runtime = self.runtime_factory(options)
                runtime.observer = self.learning.observe
                await runtime.start()
                self.runtime = runtime
            self.state, self.error = "active", ""
        except (OSError, ValueError, RuntimeError) as error:
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
                  "runtime": self.snapshot(), "learning": self.learning.status()}
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
            await self._close_runtime()
