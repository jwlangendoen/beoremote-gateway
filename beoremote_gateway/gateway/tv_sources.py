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
ENTRY_DEFAULTS = {"source_list": "tv", "launch_entity": "", "launch_source": ""}


def helper_entries(entries):
    return [{**{key: entry[key] for key in ("id", "name", "kind", "target", "slot", "callback")},
             "source_list": entry.get("source_list", "tv"), "cancel_launch": entry.get("launch_cancel", False)} for entry in entries]


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
    actions = [] if kind in {"custom", "none"} else [{"action": SERVICES[kind], "target": {"entity_id": target}}]
    launch = []
    if entry.get("launch_entity"):
        entity = entry["launch_entity"]
        variables = {"launch_player": entity, "launch_app": entry["launch_source"],
                     "launch_deadline": "{{ now().timestamp() + 20 }}",
                     # A remote's 'on' state means connected, not physically awake.
                     # Resolve by device registry, never by a guessed entity name.
                     "launch_remote": "{{ (device_entities(device_id(launch_player)) | select('match', '^remote[.]') | select('in', integration_entities('apple_tv')) | list | first | default('')) if launch_player in integration_entities('apple_tv') and device_id(launch_player) else '' }}"}
        remaining = "{{ [0, launch_deadline | float(0) - now().timestamp()] | max }}"
        ready = "{{ states(launch_player) not in ['off', 'standby', 'unknown', 'unavailable'] and (state_attr(launch_player, 'supported_features') | int(0) | bitwise_and(2048)) != 0 and launch_app in (state_attr(launch_player, 'source_list') or []) }}"
        launch += [{"if": [{"condition": "template", "value_template": "{{ trigger is defined and trigger.platform == 'webhook' and trigger.json.get('cancel', false) }}"}],
                    "then": [{"stop": "Source selection cancelled"}]},
                   {"variables": variables},
                   {"if": [{"condition": "template", "value_template": "{{ launch_remote != '' }}"}],
                    "then": [
                        {"if": [{"condition": "template", "value_template": "{{ not is_state(launch_remote, 'on') }}"}],
                         "then": [{"action": "remote.turn_on", "target": {"entity_id": "{{ launch_remote }}"}}]},
                        {"wait_template": "{{ is_state(launch_remote, 'on') }}", "timeout": remaining, "continue_on_timeout": False},
                        {"if": [{"condition": "template", "value_template": "{{ states(launch_player) in ['off', 'standby', 'unknown', 'unavailable'] }}"}],
                         "then": [{"action": "remote.send_command", "target": {"entity_id": "{{ launch_remote }}"}, "data": {"command": "wakeup"}}]}],
                    "else": []}]
        if entry.get("launch_wake"):
            launch[-1]["else"] = [{"wait_template": "{{ states(launch_player) not in ['unknown', 'unavailable'] }}", "timeout": remaining, "continue_on_timeout": False},
                                   {"if": [{"condition": "template", "value_template": "{{ states(launch_player) in ['off', 'standby'] and (state_attr(launch_player, 'supported_features') | int(0) | bitwise_and(128)) != 0 }}"}],
                                    "then": [{"action": "media_player.turn_on", "target": {"entity_id": entity}}]}]
        launch += [{"wait_template": ready, "timeout": remaining, "continue_on_timeout": False},
                   {"condition": "template", "value_template": "{{ now().timestamp() < launch_deadline | float(0) }}"},
                   {"action": "media_player.select_source", "target": {"entity_id": entity}, "data": {"source": entry["launch_source"]}}]
    return {"id": automation_id(tv, entry["id"]), "alias": "Beoremote source · " + entry["name"],
            "description": "Managed by Beoremote Gateway source setup.", "mode": "restart" if launch else "single", "max_exceeded": "silent",
            "triggers": [{"trigger": "webhook", "webhook_id": webhook, "allowed_methods": ["POST"], "local_only": True}],
            # Reject stale/foreign webhooks before restart can cancel a valid run.
            "conditions": [{"condition": "template", "value_template": guard}] if launch else [],
            "actions": [{"condition": "template", "value_template": guard}, *launch, *actions]}


def validate_entry(data, status, old=None):
    required = {"id", "name", "kind", "target", "action_kind", "action_target"}
    if not isinstance(data, dict) or not required <= set(data) or set(data) - required - ENTRY_DEFAULTS.keys():
        raise ValueError("Reload the source editor and try again.")
    entry = {**ENTRY_DEFAULTS, **data}
    if not all(isinstance(value, str) for value in entry.values()):
        raise ValueError("Choose the source values from the editor.")
    if not isinstance(entry["name"], str) or not 1 <= len(entry["name"].strip()) <= 32 or any(ord(c) < 32 for c in entry["name"]):
        raise ValueError("Give this source a name of 1–32 characters.")
    entry["name"] = entry["name"].strip()
    if entry["source_list"] not in {"tv", "music"}:
        raise ValueError("Choose MUSIC or TV for the remote source list.")
    if entry["source_list"] == "music" and "music" not in status.get("source_lists", []):
        raise ValueError("Update TV Support before adding MUSIC sources. Your existing sources are kept.")
    if entry["launch_entity"]:
        if entry["kind"] != "hdmi" or not re.fullmatch(r"media_player\.[a-z0-9_]+", entry["launch_entity"]) or not 1 <= len(entry["launch_source"]) <= 256 or any(ord(c) < 32 for c in entry["launch_source"]):
            raise ValueError("Choose a connected media player and an app or source from its list.")
    elif entry["launch_source"]:
        raise ValueError("Choose the device that opens this app or source.")
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
            row = {**public, "source_list": item.get("source_list", "tv"),
                   "launch_entity": entry.get("launch_entity", ""), "launch_source": entry.get("launch_source", ""),
                   "action_kind": entry.get("action_kind", "none"), "action_target": entry.get("action_target", "")}
            if entry.get("webhook"):
                row["edit_path"] = "/config/automation/edit/" + automation_id(tv, item["id"])
            rows.append(row)
        # Explicit projection: callback capabilities and TV originals never reach the UI.
        return {key: status[key] for key in ("state", "error", "revision", "version", "source_lists", "source_order", "source_cancel", "catalog", "slots", "inputs", "apps", "legacy_trusted", "legacy_sources") if key in status} | {"entries": rows, "can_restore": self.path(tv, True).exists()}

    async def media_players(self):
        players = []
        for state in await self.actions.ha.states():
            entity, attrs = state.get("entity_id", ""), state.get("attributes", {})
            features = attrs.get("supported_features", 0)
            sources = attrs.get("source_list", [])
            if (not re.fullmatch(r"media_player\.[a-z0-9_]+", entity) or state.get("state") == "unavailable"
                    or type(features) is not int or not features & 2048 or not isinstance(sources, list)):
                continue
            names = sorted({s for s in sources if isinstance(s, str) and 1 <= len(s) <= 256 and not any(ord(c) < 32 for c in s)}, key=str.casefold)
            if names:
                players.append({"id": entity, "name": attrs.get("friendly_name") or entity,
                                "sources": [{"id": s, "name": s} for s in names], "wake": bool(features & 128)})
        return sorted(players, key=lambda p: (p["name"].casefold(), p["id"]))

    async def targets(self):
        return {**await self.actions.targets(), "media_players": await self.media_players()}

    async def wait_ready(self, adb, address, tv, operation=None, version=None):
        for _ in range(20):
            status = await self.status(adb, address, tv)
            raw = await adb.helper_call(address, "status") if operation else None
            if status.get("state") == "attention":
                raise ValueError(status.get("error", "TV Support needs attention."))
            if status.get("state") == "ready" and (version is None or status.get("version") == version) and (not operation or raw.get("operation") == operation):
                return status
            await asyncio.sleep(.4)
        raise ValueError("TV Support is still working. Refresh its status before trying again.")

    async def apply(self, adb, address, tv, config, expected, order_check=None):
        operation = secrets.token_hex(16)
        next_config = {**config, "owner": self.owner, "tv": tv, "revision": config.get("revision") or secrets.token_hex(16)}
        request = {"operation": operation, "expected": expected, "config": next_config}
        if order_check is not None:
            request["order_check"] = order_check
        await adb.helper_call(address, "apply", request)
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
        if entry["launch_entity"]:
            if not status.get("source_cancel"):
                raise ValueError("Update TV Support in Configuration before saving a connected-device app.")
            player = next((p for p in await self.media_players() if p["id"] == entry["launch_entity"]), None)
            if player is None or not any(s["id"] == entry["launch_source"] for s in player["sources"]):
                raise ValueError("This device or app is unavailable. Refresh and choose it from Home Assistant's current list.")
            entry["launch_wake"] = player["wake"]
        if entry["action_kind"] != "none" or entry["launch_entity"]:
            configuration = await self.actions.ha.request("GET", "config")
            if not isinstance(configuration, dict) or "webhook" not in configuration.get("components", []):
                raise ValueError("Home Assistant's webhook integration is unavailable. Enable it before linking a source action.")
        if entry["action_kind"] in GROUPS:
            targets = await self.actions.targets()
            if not any(item["id"] == entry["action_target"] for item in targets[GROUPS[entry["action_kind"]]]):
                raise ValueError("This Home Assistant action is unavailable or needs inputs. Use the Home Assistant editor instead.")
        if old:
            entry.update({key: old[key] for key in ("webhook", "action_hash", "launch_cancel") if key in old})
        key = automation_id(tv, entry["id"])
        before = await self.actions.ha.request("GET", "config/automation/config/" + key)
        same_action = old and all(entry.get(field, ENTRY_DEFAULTS.get(field, False)) == old.get(field, ENTRY_DEFAULTS.get(field, False)) for field in ("action_kind", "action_target", "launch_entity", "launch_source", "launch_wake"))
        if same_action and entry["launch_entity"] and before is not None and digest(before) == old.get("action_hash"):
            same_action = before == automation(tv, entry, entry.get("webhook", ""))
        if before is not None and (old is None or digest(before) != old.get("action_hash")) and not same_action:
            raise ValueError("This source's automation was edited in Home Assistant. Keep or edit that action there.")
        after = before
        if not same_action:
            if entry["action_kind"] == "none" and not entry["launch_entity"]:
                entry.pop("webhook", None)
                entry.pop("action_hash", None)
                after = None
            else:
                entry["webhook"] = entry.get("webhook") or secrets.token_hex(32)
                after = automation(tv, entry, entry["webhook"])
                entry["action_hash"] = digest(after)
                entry["launch_cancel"] = bool(entry["launch_entity"])
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
        config = {**{key: backup["config"][key] for key in ("order",) if key in backup["config"]},
                  "revision": secrets.token_hex(16), "entries": helper_entries(entries)}
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
        await self.apply(adb, address, tv, {**{key: backup["config"][key] for key in ("order",) if key in backup["config"]}, "entries": helper_entries(entries)}, revision)
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
        current = await self.actions.ha.request("GET", "config/automation/config/" + key) if key is not None else None
        if current != backup["after"] and current != backup["before"]:
            raise ValueError("The source automation changed in Home Assistant. Review it there before restoring.")
        if key is not None and current != backup["before"]:
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

    async def reorder(self, adb, address, tv, revision, source_list, ids):
        status = await self.status(adb, address, tv)
        if status.get("state") != "ready" or status.get("revision", "") != revision:
            raise ValueError("The TV setup changed or is not ready. Refresh and try again.")
        if status.get("source_order") is not True:
            raise ValueError("Update TV Support in Configuration before changing source order.")
        if status.get("legacy_sources", 0) > 0:
            raise ValueError("Replace the previous source helper in Configuration before changing source order.")
        if not isinstance(source_list, str) or source_list not in {"tv", "music"} or not isinstance(ids, list) or len(ids) > 256 or not all(isinstance(i, str) and 1 <= len(i) <= 128 for i in ids):
            raise ValueError("Choose sources from the current MUSIC or TV list.")
        current = [row["id"] for row in status.get("catalog", []) if row.get("source_list") == source_list]
        if len(set(ids)) != len(ids) or set(ids) != set(current):
            raise ValueError("The source list changed. Refresh before changing its order.")
        if ids == current:
            return status
        store = self.load(tv)
        backup = await adb.helper_call(address, "backup")
        config = {**backup["config"], "revision": secrets.token_hex(16),
                  "order": {**backup["config"].get("order", {}), source_list: ids}}
        previous = {**backup["config"], "order": {group: [row["id"] for row in status.get("catalog", []) if row.get("source_list") == group] for group in ("tv", "music")}}
        private_write(self.path(tv, True), {"helper": previous, "store": store,
                                          "automation_id": None, "before": None, "after": None})
        try:
            await self.apply(adb, address, tv, config, revision, {"source_list": source_list, "ids": ids})
        except Exception as error:
            try:
                observed = await adb.helper_call(address, "backup")
                if observed["config"].get("revision") == config["revision"]:
                    return await self.status(adb, address, tv)
            except Exception:
                pass
            if isinstance(error, ValueError):
                raise error
            raise ValueError("The order was not confirmed. Refresh or restore the previous setup before continuing.") from error
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
