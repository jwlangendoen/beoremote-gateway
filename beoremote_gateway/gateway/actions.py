"""Create ordinary HA automations for learned buttons; only manage our own rules."""
import asyncio
import hashlib
import re

from .ha import HAError, HomeAssistant
from .learning import light_press

MARKER = "Managed by Beoremote Gateway."
RULE = re.compile(r"beoremote_gateway_[0-9a-f]{20}")
ENTITY = re.compile(r"(?:scene|light)\.[a-z0-9_]+")
FRESH = "{{ trigger is defined and trigger.platform == 'event' and trigger.event is defined and 0 <= (now().timestamp() - (trigger.event.data.get('received_at', 0) | float(0))) < 2 }}"


def rule_id(event):
    payload = light_press(event)
    if payload is None or not isinstance(event.get("peer_jid"), str):
        raise ValueError("This is not a learned LIGHT button.")
    identity = event["peer_jid"] + "\0" + payload
    return "beoremote_gateway_" + hashlib.sha256(identity.encode()).hexdigest()[:20]


def make_rule(event, name, kind, target):
    if (not isinstance(name, str) or not 1 <= len(name.strip()) <= 64
            or any(ord(char) < 32 for char in name)):
        raise ValueError("Give this button a name of 1–64 characters.")
    if (kind not in ("scene", "light_off") or not isinstance(target, str)
            or not ENTITY.fullmatch(target)
            or not target.startswith("scene." if kind == "scene" else "light.")):
        raise ValueError("Choose a scene or light from Home Assistant.")
    return {"id": rule_id(event), "alias": "Beoremote · " + name.strip(), "description": MARKER,
            "mode": "queued", "max": 5, "max_exceeded": "silent",
            "triggers": [{"trigger": "event", "event_type": "beoremote_telegram", "event_data": {
                "peer_jid": event["peer_jid"], "originator": "0", "data_hex": event["data_hex"]}}],
            "conditions": [], "actions": [
                {"condition": "template", "value_template": FRESH},
                {"action": "scene.turn_on" if kind == "scene" else "light.turn_off",
                 "target": {"entity_id": target}}]}


def owned_rule(config, key):
    if not isinstance(config, dict) or config.get("description") != MARKER or not RULE.fullmatch(key):
        return None
    try:
        triggers = config["triggers"]
        if (len(triggers) != 1 or triggers[0]["trigger"] != "event"
                or triggers[0]["event_type"] != "beoremote_telegram"):
            return None
        event = triggers[0]["event_data"]
        if rule_id(event) != key or config["id"] != key:
            return None
        name = str(config.get("alias", "My LIGHT button")).removeprefix("Beoremote · ")
        customized = {"id": key, "name": name, "tv_jid": event["peer_jid"], "customized": True}
    except (KeyError, TypeError, ValueError, IndexError):
        return None
    try:
        action = config["actions"][1]
        kind = {"scene.turn_on": "scene", "light.turn_off": "light_off"}.get(action["action"])
        standard = make_rule(event, name, kind, action["target"]["entity_id"])
        # Preserve anything edited beyond the simple form in Home Assistant.
        if config != standard:
            return customized
        return {"id": key, "name": name, "tv_jid": event["peer_jid"], "customized": False,
                "kind": kind, "target": action["target"]["entity_id"]}
    except (KeyError, TypeError, ValueError, IndexError):
        return customized


class ActionManager:
    def __init__(self, ha=None):
        self.ha = ha or HomeAssistant()
        self.lock = asyncio.Lock()

    async def targets(self):
        return self._targets(await self.ha.states())

    @staticmethod
    def _targets(states):
        result = {"scenes": [], "lights": []}
        for state in states:
            entity = state.get("entity_id", "")
            if not ENTITY.fullmatch(entity) or state.get("state") == "unavailable":
                continue
            group = "scenes" if entity.startswith("scene.") else "lights"
            result[group].append({"id": entity, "name": state.get("attributes", {}).get("friendly_name") or entity})
        for items in result.values():
            items.sort(key=lambda item: (item["name"].casefold(), item["id"]))
        return result

    async def list(self, jid):
        states = await self.ha.states()
        entities = {state.get("attributes", {}).get("id"): state for state in states
                    if state.get("entity_id", "").startswith("automation.")
                    and isinstance(state.get("attributes", {}).get("id"), str)
                    and RULE.fullmatch(state["attributes"]["id"])}
        if len(entities) > 128:
            raise HAError("Too many gateway actions to display. Manage them in Home Assistant.")
        limit = asyncio.Semaphore(4)

        async def read(key, state):
            async with limit:
                config = await self.ha.request("GET", "config/automation/config/" + key)
            rule = owned_rule(config, key)
            if rule is None or rule["tv_jid"] != jid:
                return None
            target = next((item for item in states if item.get("entity_id") == rule.get("target")), {})
            return {"id": key, "name": rule["name"], "kind": rule.get("kind"),
                    "target": rule.get("target"), "target_name": target.get("attributes", {}).get("friendly_name") or rule.get("target", ""),
                    "enabled": state.get("state") == "on", "customized": rule["customized"],
                    "edit_path": "/config/automation/edit/" + key}

        rules = await asyncio.gather(*(read(key, state) for key, state in entities.items()))
        return sorted((rule for rule in rules if rule is not None), key=lambda rule: rule["name"].casefold())

    async def _entity(self, key):
        for attempt in range(6):
            states = await self.ha.states()
            match = next((state for state in states if state.get("entity_id", "").startswith("automation.")
                          and state.get("attributes", {}).get("id") == key), None)
            if match is not None:
                return match["entity_id"]
            if attempt < 5:
                await asyncio.sleep(0.2)
        raise HAError("The action is saved, but Home Assistant has not loaded it yet. Refresh the action list shortly.")

    async def _reload(self, key):
        try:
            await self.ha.request("POST", "services/automation/reload", {"id": key})
        except HAError as error:
            if error.status != 400:
                raise
            # Older HA versions reload all automations, as their normal editor does.
            await self.ha.request("POST", "services/automation/reload", {})

    async def save(self, event, name, kind, target):
        config = make_rule(event, name, kind, target)
        key = config["id"]
        async with self.lock:
            return await self._save(config, name, kind, target)

    async def update(self, key, jid, name, kind, target):
        async with self.lock:
            await self._owned(key, jid)
            existing = await self.ha.request("GET", "config/automation/config/" + key)
            config = make_rule(existing["triggers"][0]["event_data"], name, kind, target)
            return await self._save(config, name, kind, target)

    async def _save(self, config, name, kind, target):
        key = config["id"]
            targets = await self.targets()
            group = targets["scenes" if kind == "scene" else "lights"]
            if not any(item["id"] == target for item in group):
                raise ValueError("This scene or light is no longer available. Choose another one.")
            existing = await self.ha.request("GET", "config/automation/config/" + key)
            if existing is not None:
                owned = owned_rule(existing, key)
                if owned is None or owned["customized"]:
                    raise ValueError("An existing automation for this button was edited outside this app. Review it in Home Assistant first.")
            if existing != config:
                await self.ha.request("POST", "config/automation/config/" + key, config)
            await self._reload(key)
            entity = await self._entity(key)
            await self.ha.request("POST", "services/automation/turn_on", {"entity_id": entity})
        return {"id": key, "name": name.strip(), "edit_path": "/config/automation/edit/" + key}

    async def _owned(self, key, jid):
        if not isinstance(key, str) or not RULE.fullmatch(key):
            raise ValueError("Choose an action created by this app.")
        config = await self.ha.request("GET", "config/automation/config/" + key)
        rule = owned_rule(config, key)
        if rule is None or rule["tv_jid"] != jid or rule["customized"]:
            raise ValueError("Manage this automation in Home Assistant; it is not an unchanged action from this app.")
        return rule

    async def toggle(self, key, jid, enabled):
        if type(enabled) is not bool:
            raise ValueError("Choose whether the action should be enabled.")
        async with self.lock:
            await self._owned(key, jid)
            entity = await self._entity(key)
            await self.ha.request("POST", "services/automation/turn_on" if enabled else "services/automation/turn_off",
                                  {"entity_id": entity})

    async def remove(self, key, jid):
        async with self.lock:
            await self._owned(key, jid)
            entity = await self._entity(key)
            await self.ha.request("POST", "services/automation/turn_off", {"entity_id": entity})
            await self.ha.request("DELETE", "config/automation/config/" + key)
