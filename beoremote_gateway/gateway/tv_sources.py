"""Scoped source editing and ordinary HA webhook automations. No TV access on reads."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import tempfile

from .actions import GROUPS, SERVICES

ID = re.compile(r"BGW_[a-f0-9]{12}")
REVISION = re.compile(r"[a-f0-9]{32}")
EMPTY = {"entries": []}


def private_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, prefix=".source-", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def automation_id(tv, entry_id):
    return "beoremote_source_" + hashlib.sha256((tv + ":" + entry_id).encode()).hexdigest()[:20]


def automation(tv, entry, webhook):
    kind, target = entry["action_kind"], entry["action_target"]
    guard = "{{ trigger is defined and (trigger.platform != 'webhook' or (trigger.json is defined and trigger.json.get('source') == '" + entry["id"] + "' and trigger.json.get('tv') == '" + tv + "' and 0 <= (now().timestamp() - (trigger.json.get('created_at', 0) | float(0))) < 5)) }}"
    actions = [] if kind == "custom" else [{"action": SERVICES[kind], "target": {"entity_id": target}}]
    return {"id": automation_id(tv, entry["id"]), "alias": "Beoremote source · " + entry["name"],
            "description": "Managed by Beoremote Gateway source setup.", "mode": "single", "max_exceeded": "silent",
            "triggers": [{"trigger": "webhook", "webhook_id": webhook, "allowed_methods": ["POST"], "local_only": True}],
            "conditions": [], "actions": [{"condition": "template", "value_template": guard}, *actions]}


def validate_entry(data, status, old=None):
    if not isinstance(data, dict) or set(data) != {"id", "name", "kind", "target", "action_kind", "action_target"}:
        raise ValueError("Reload the source editor and try again.")
    entry = dict(data)
    if not all(isinstance(value, str) for value in entry.values()):
        raise ValueError("Choose the source values from the editor.")
    if not isinstance(entry["name"], str) or not 1 <= len(entry["name"].strip()) <= 32 or any(ord(c) < 32 for c in entry["name"]):
        raise ValueError("Give this source a name of 1–32 characters.")
    entry["name"] = entry["name"].strip()
    if old is None:
        if entry["id"] != "":
            raise ValueError("Choose a saved source to change it.")
        free = [slot["slot"] for slot in status.get("slots", []) if slot.get("free") is True and type(slot.get("slot")) is int and 0 <= slot["slot"] < 8]
        if not free:
            raise ValueError("There is no free source slot. Remove an existing shortcut first.")
        entry.update(id="BGW_" + secrets.token_hex(6), slot=free[0])
    else:
        entry["slot"] = old["slot"]
    if entry["kind"] == "app":
        available = {app["package"] for app in status.get("apps", [])}
    elif entry["kind"] == "hdmi":
        available = {item["id"] for item in status.get("inputs", [])}
    else:
        raise ValueError("Choose a TV app or an HDMI input.")
    if entry["target"] not in available:
        raise ValueError("Choose an available TV app or HDMI input from the list.")
    if entry["action_kind"] not in {"none", "custom", "scene", "script", "light_off"}:
        raise ValueError("Choose a Home Assistant action.")
    if not isinstance(entry["action_target"], str) or (entry["action_kind"] in {"none", "custom"} and entry["action_target"]):
        raise ValueError("Choose the action from the list.")
    return entry


class TVSources:
    def __init__(self, directory, actions):
        self.directory = Path(directory) / "tv-sources"
        self.actions = actions
        path = self.directory / "owner.json"
        if path.exists():
            self.owner = json.loads(path.read_text())["id"]
        else:
            self.owner = secrets.token_hex(16)
            private_write(path, {"id": self.owner})
        if not REVISION.fullmatch(self.owner):
            raise ValueError("Saved TV Support identity is invalid.")

    def path(self, tv, backup=False):
        name = hashlib.sha256(tv.encode()).hexdigest()[:20]
        return self.directory / (name + ("-previous.json" if backup else ".json"))

    def load(self, tv):
        path = self.path(tv)
        if path.exists():
            if path.stat().st_size > 131072:
                raise ValueError("Saved TV sources are too large.")
            return json.loads(path.read_text())
        return {"entries": []}

    async def status(self, adb, address, tv):
        status = await adb.helper_call(address, "status")
        if status.get("tv") not in (None, tv):
            raise ValueError("TV Support belongs to a different TV. No sources were changed.")
        if status.get("owner") not in (None, "", self.owner):
            raise ValueError("These sources are managed by another gateway installation.")
        store = self.load(tv)
        saved = {entry["id"]: entry for entry in store["entries"]}
        rows = []
        for item in status.get("entries", []):
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not ID.fullmatch(item["id"]):
                raise ValueError("TV Support returned an invalid source list.")
            entry = saved.get(item["id"], {})
            public = {key: item[key] for key in ("id", "name", "kind", "target", "slot")}
            row = {**public, "action_kind": entry.get("action_kind", "none"), "action_target": entry.get("action_target", "")}
            if entry.get("webhook"):
                row["edit_path"] = "/config/automation/edit/" + automation_id(tv, item["id"])
            rows.append(row)
        # Explicit projection: callback capabilities and TV originals never reach the UI.
        return {key: status[key] for key in ("state", "error", "revision", "version", "slots", "inputs", "apps", "legacy_trusted", "legacy_sources") if key in status} | {"entries": rows, "can_restore": self.path(tv, True).exists()}

    async def wait_ready(self, adb, address, tv, operation=None):
        for _ in range(20):
            status = await self.status(adb, address, tv)
            raw = await adb.helper_call(address, "status") if operation else None
            if status.get("state") == "attention":
                raise ValueError(status.get("error", "TV Support needs attention."))
            if status.get("state") == "ready" and (not operation or raw.get("operation") == operation):
                return status
            await asyncio.sleep(.4)
        raise ValueError("TV Support is still working. Refresh its status before trying again.")

    async def apply(self, adb, address, tv, config, expected):
        operation = secrets.token_hex(16)
        next_config = {**config, "owner": self.owner, "tv": tv, "revision": config.get("revision") or secrets.token_hex(16)}
        await adb.helper_call(address, "apply", {"operation": operation, "expected": expected, "config": next_config})
        return await self.wait_ready(adb, address, tv, operation)

    async def _set_automation(self, key, config, initial_enabled=True):
        if not isinstance(key, str) or not re.fullmatch(r"beoremote_source_[a-f0-9]{20}", key):
            raise ValueError("Choose an automation created by source setup.")
        ha = self.actions.ha
        states = await ha.states()
        state = next((s for s in states if s.get("entity_id", "").startswith("automation.") and s.get("attributes", {}).get("id") == key), None)
        enabled = initial_enabled if state is None else state.get("state") == "on"
        if config is None:
            if state:
                await ha.request("POST", "services/automation/turn_off", {"entity_id": state["entity_id"]})
            await ha.request("DELETE", "config/automation/config/" + key)
        else:
            await ha.request("POST", "config/automation/config/" + key, config)
            await self.actions._reload(key)
            entity = await self.actions._entity(key)
            await ha.request("POST", "services/automation/turn_on" if enabled else "services/automation/turn_off", {"entity_id": entity})

    async def _enabled(self, key):
        states = await self.actions.ha.states()
        return next((s.get("state") == "on" for s in states if s.get("attributes", {}).get("id") == key), True)

    async def save(self, adb, address, local, tv, revision, data):
        status = await self.status(adb, address, tv)
        if status.get("state") != "ready" or status.get("revision", "") != revision:
            raise ValueError("The TV setup changed or is not ready. Refresh and try again.")
        store = self.load(tv)
        old = next((e for e in store["entries"] if e["id"] == data.get("id")), None)
        entry = validate_entry(data, status, old)
        if entry["action_kind"] != "none":
            configuration = await self.actions.ha.request("GET", "config")
            if not isinstance(configuration, dict) or "webhook" not in configuration.get("components", []):
                raise ValueError("Home Assistant's webhook integration is unavailable. Enable it before linking a source action.")
        if entry["action_kind"] in GROUPS:
            targets = await self.actions.targets()
            if not any(item["id"] == entry["action_target"] for item in targets[GROUPS[entry["action_kind"]]]):
                raise ValueError("This Home Assistant action is unavailable or needs inputs. Use the Home Assistant editor instead.")
        if old:
            entry.update({key: old[key] for key in ("webhook", "action_hash") if key in old})
        key = automation_id(tv, entry["id"])
        before = await self.actions.ha.request("GET", "config/automation/config/" + key)
        same_action = old and all(entry[field] == old[field] for field in ("action_kind", "action_target"))
        if before is not None and (old is None or digest(before) != old.get("action_hash")) and not same_action:
            raise ValueError("This source's automation was edited in Home Assistant. Keep or edit that action there.")
        after = before
        if not same_action:
            if entry["action_kind"] == "none":
                entry.pop("webhook", None)
                entry.pop("action_hash", None)
                after = None
            else:
                entry["webhook"] = entry.get("webhook") or secrets.token_hex(32)
                after = automation(tv, entry, entry["webhook"])
                entry["action_hash"] = digest(after)
        elif old and old.get("webhook"):
            entry["webhook"] = old["webhook"]
        callback = f"http://{local}:8123/api/webhook/{entry['webhook']}" if entry.get("webhook") else ""
        entry["callback"] = callback
        entries = [entry if old and e["id"] == old["id"] else e for e in store["entries"]]
        if old is None:
            entries.append(entry)
        backup = await adb.helper_call(address, "backup")
        journal = {"helper": backup["config"], "store": store, "automation_id": key, "before": before, "after": after, "enabled": await self._enabled(key)}
        private_write(self.path(tv, True), journal)
        if after != before and after is not None:
            await self._set_automation(key, after)
        config = {"revision": secrets.token_hex(16), "entries": [{k: e[k] for k in ("id", "name", "kind", "target", "slot", "callback")} for e in entries]}
        try:
            await self.apply(adb, address, tv, config, revision)
        except Exception as error:
            # A lost ADB reply is not proof of failure. Do not undo an automation
            # that a successfully committed source may already reference.
            try:
                observed = await adb.helper_call(address, "backup")
                if observed["config"].get("revision") == config["revision"]:
                    private_write(self.path(tv), {"entries": entries})
                    return await self.status(adb, address, tv)
            except Exception:
                pass
            raise ValueError("Saving was not confirmed. Refresh the sources or use Restore previous setup before trying again.") from error
        private_write(self.path(tv), {"entries": entries})
        if after is None and before is not None and digest(before) == (old or {}).get("action_hash"):
            await self._set_automation(key, None)
        return await self.status(adb, address, tv)

    async def remove(self, adb, address, tv, revision, entry_id):
        store = self.load(tv)
        old = next((e for e in store["entries"] if e["id"] == entry_id), None)
        if old is None:
            raise ValueError("Choose a source created by this gateway.")
        status = await self.status(adb, address, tv)
        if status.get("revision", "") != revision:
            raise ValueError("The TV setup changed. Refresh before removing a source.")
        backup = await adb.helper_call(address, "backup")
        key = automation_id(tv, entry_id)
        before = await self.actions.ha.request("GET", "config/automation/config/" + key)
        remove_action = before is not None and digest(before) == old.get("action_hash")
        private_write(self.path(tv, True), {"helper": backup["config"], "store": store, "automation_id": key, "before": before, "after": None if remove_action else before, "enabled": await self._enabled(key)})
        entries = [e for e in store["entries"] if e["id"] != entry_id]
        await self.apply(adb, address, tv, {"entries": [{k: e[k] for k in ("id", "name", "kind", "target", "slot", "callback")} for e in entries]}, revision)
        private_write(self.path(tv), {"entries": entries})
        if remove_action:
            await self._set_automation(key, None)
        return await self.status(adb, address, tv)

    async def restore(self, adb, address, tv, revision):
        path = self.path(tv, True)
        if not path.exists():
            raise ValueError("No previous source setup is available.")
        backup = json.loads(path.read_text())
        key = backup["automation_id"]
        current = await self.actions.ha.request("GET", "config/automation/config/" + key)
        if current != backup["after"] and current != backup["before"]:
            raise ValueError("The source automation changed in Home Assistant. Review it there before restoring.")
        if current != backup["before"]:
            await self._set_automation(key, backup["before"], initial_enabled=backup.get("enabled", True))
        config = {**backup["helper"], "revision": secrets.token_hex(16)}
        try:
            await self.apply(adb, address, tv, config, revision)
        except Exception as error:
            try:
                observed = await adb.helper_call(address, "backup")
                if observed["config"].get("revision") == config["revision"]:
                    private_write(self.path(tv), backup["store"])
                    return await self.status(adb, address, tv)
            except Exception:
                pass
            raise ValueError("Restoring was not confirmed. Keep the backup and refresh before trying again.") from error
        private_write(self.path(tv), backup["store"])
        return await self.status(adb, address, tv)

    async def refresh(self, adb, address, tv):
        await self.status(adb, address, tv)
        operation = secrets.token_hex(16)
        await adb.helper_call(address, "refresh", {"operation": operation})
        return await self.wait_ready(adb, address, tv, operation)

    async def test(self, adb, address, tv, entry_id):
        status = await self.status(adb, address, tv)
        if not any(row["id"] == entry_id for row in status["entries"]):
            raise ValueError("Save this source before testing it.")
        operation = secrets.token_hex(16)
        await adb.helper_call(address, "test", {"id": entry_id, "operation": operation})
        await self.wait_ready(adb, address, tv, operation)
        return {"sent": True}
