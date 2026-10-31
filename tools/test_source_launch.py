"""Execute generated source automations in real HA Core, with virtual devices only.

Run in the official HA container with --network none and this repository mounted
read-only at /repo. No household settings, credentials or devices are needed.
"""
import asyncio
import copy
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import sys
import tempfile
from types import MappingProxyType

from homeassistant.config_entries import ConfigEntry, ConfigEntryDisabler
from homeassistant.bootstrap import async_from_config_dict
from homeassistant import loader
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "beoremote_gateway"))
from gateway.tv_sources import automation

TV = "7980.1234567.12345678@products.bang-olufsen.com"
PLAYER = "media_player.fixture_box"
REMOTE = "remote.renamed_box"
SOURCE = "BGW_123456789abc"


async def main():
    with tempfile.TemporaryDirectory() as directory:
        hass = HomeAssistant(directory)
        loader.async_setup(hass)
        calls = []
        fail_launch = False

        def player(state="idle", apps=None, features=2176):
            hass.states.async_set(PLAYER, state, {"supported_features": features,
                                  "source_list": ["Netflix", "YouTube"] if apps is None else apps})

        async def service(call):
            nonlocal fail_launch
            calls.append((call.domain + "." + call.service, dict(call.data)))
            if call.domain == "remote" and call.service == "turn_on":
                hass.states.async_set(REMOTE, "on")
            if call.service == "select_source" and fail_launch:
                raise HomeAssistantError("Virtual launch failure")

        for domain, names in {"remote": ["turn_on", "send_command"],
                              "media_player": ["turn_on", "select_source", "media_pause"], "scene": ["turn_on"]}.items():
            for name in names:
                hass.services.async_register(domain, name, service)
        assert await async_from_config_dict({"homeassistant": {"country": "NL", "time_zone": "Europe/Amsterdam", "latitude": 0, "longitude": 0}}, hass)
        logging.basicConfig(level=logging.WARNING, force=True)
        entry = ConfigEntry(domain="apple_tv", title="Virtual box", data={}, options={},
                            source="user", unique_id="virtual-box", version=1, minor_version=1,
                            discovery_keys=MappingProxyType({}), subentries_data=[], disabled_by=ConfigEntryDisabler.USER)
        # Register metadata only. ConfigEntries.async_add also starts integration
        # setup and discovery, which this network-isolated fixture must not do.
        hass.config_entries._entries[entry.entry_id] = entry
        devices = dr.async_get(hass)
        device = devices.async_get_or_create(config_entry_id=entry.entry_id, identifiers={("apple_tv", "virtual-box")})
        registry = er.async_get(hass)
        for domain, name in (("media_player", "fixture_box"), ("remote", "renamed_box")):
            registry.async_get_or_create(domain, "apple_tv", "virtual-" + domain,
                                         suggested_object_id=name, config_entry=entry, device_id=device.id)
        from homeassistant.helpers.entity import entity_sources
        entity_sources(hass)[PLAYER] = {"domain": "apple_tv"}
        entity_sources(hass)[REMOTE] = {"domain": "apple_tv"}
        player()
        hass.states.async_set(REMOTE, "on")
        config = automation(TV, {"id": SOURCE, "name": "Fixture Netflix", "action_kind": "scene",
                            "action_target": "scene.fixture", "launch_entity": PLAYER,
                            "launch_source": "Netflix", "launch_wake": True}, "a" * 64)
        short = copy.deepcopy(config)
        short.update(id="beoremote_source_" + "b" * 20, alias="Fixture short deadline")
        short["triggers"][0]["webhook_id"] = "b" * 64
        next(a["variables"] for a in short["actions"] if "variables" in a)["launch_deadline"] = "{{ now().timestamp() + 0.3 }}"
        generic = automation(TV, {"id": "BGW_abcdefabcdef", "name": "Fixture generic", "action_kind": "none",
                              "action_target": "", "launch_entity": "media_player.generic",
                              "launch_source": "Game", "launch_wake": False}, "c" * 64)
        from homeassistant.components import automation as automation_component
        assert await async_setup_component(hass, "automation", {})
        from homeassistant.components.automation.config import async_validate_config
        validated = await async_validate_config(hass, {"automation": [config, short, generic]})
        await automation_component._async_process_config(hass, validated, hass.data["automation"])
        await hass.async_block_till_done()
        assert list(hass.data["automation"].entities), "Generated automation did not load"
        # Domain setup during validation registers its normal entity services.
        # Replace only device-facing services with virtual recorders afterwards.
        for domain, names in {"remote": ["turn_on", "send_command"],
                              "media_player": ["turn_on", "select_source", "media_pause"], "scene": ["turn_on"]}.items():
            for name in names:
                hass.services.async_register(domain, name, service)
        entity = next(e for e in hass.data["automation"].entities if e.unique_id == config["id"])
        checks = []

        async def fire(target=entity, **changes):
            payload = {"tv": TV, "source": SOURCE, "created_at": datetime.now(UTC).timestamp(), **changes}
            await target.async_trigger({"trigger": {"platform": "webhook", "json": payload}}, skip_condition=False)

        async def settle():
            await asyncio.sleep(.1)

        def selected():
            return [data["source"] for name, data in calls if name == "media_player.select_source"]

        async def begin(state="off", apps=None, features=2176, remote="on"):
            calls.clear()
            player(state, apps, features)
            hass.states.async_set(REMOTE, remote)
            task = asyncio.create_task(fire())
            await settle()
            return task

        await fire()
        assert selected() == ["Netflix"] and calls[-1][0] == "scene.turn_on"
        assert not any(name in ("remote.turn_on", "remote.send_command", "media_player.turn_on") for name, _ in calls)
        checks.append("already_awake_launches_once_without_wake")

        task = await begin(remote="off")
        assert [name for name, _ in calls] == ["remote.turn_on", "remote.send_command"], calls
        assert calls[-1][1]["command"] == "wakeup"
        assert calls[-1][1]["entity_id"] == [REMOTE]
        player("idle", apps=[])
        await settle()
        assert not selected()
        player()
        await task
        assert selected() == ["Netflix"]
        checks.append("disconnected_apple_tv_connects_and_wakes_via_its_registered_remote")

        task = await begin(apps=[])
        await asyncio.sleep(5.2)
        player()
        await task
        assert selected() == ["Netflix"]
        checks.append("slow_start_beyond_old_five_second_guard_succeeds")

        for label, changes in (("source_switch", {"cancel": True}), ("standby", {"cancel": True})):
            task = await begin(apps=[])
            await fire(**changes)
            player()
            await task
            assert not selected() and not any(name == "scene.turn_on" for name, _ in calls)
            checks.append(label + "_cancels_pending_launch_and_extra_action")

        task = await begin(apps=[])
        for changes in ({"tv": "other"}, {"source": "BGW_abcdefabcdef"}, {"created_at": 0},
                        {"created_at": datetime.now(UTC).timestamp() + 30}):
            await fire(cancel=True, **changes)
        player()
        await task
        assert selected() == ["Netflix"]
        checks.append("stale_future_foreign_cancellations_cannot_interrupt_valid_request")

        task = await begin(apps=[])
        newer = asyncio.create_task(fire())
        await settle()
        player()
        await asyncio.gather(task, newer)
        assert selected() == ["Netflix"]
        checks.append("repeated_selection_restarts_without_queued_duplicate")

        task = await begin(apps=[], features=128)
        player("idle", apps=["Netflix"], features=128)
        await settle()
        assert not selected()
        player()
        await task
        assert selected() == ["Netflix"]
        checks.append("app_name_without_launch_capability_is_not_ready")

        # A completed external source must be paused, never re-opened, on exit.
        calls.clear()
        player("playing", features=2177)
        await fire(pause=True)
        assert [name for name, _ in calls] == ["media_player.media_pause"], calls
        checks.append("leaving_external_input_pauses_without_launch_wake_or_extra_scene")
        for state, features in (("paused",2177),("off",2177),("unavailable",2177),("playing",2176)):
            calls.clear();player(state,features=features)
            await fire(pause=True)
            assert not calls, calls
        checks.append("exit_does_not_wake_or_toggle_paused_off_unavailable_or_unsupported_players")
        for payload in ({"created_at":0},{"tv":"other"},{"source":"BGW_abcdefabcdef"}):
            calls.clear();player("playing",features=2177)
            await fire(pause=True,**payload)
            assert not calls
        checks.append("foreign_and_stale_exit_notifications_are_ignored")
        # A newer selection invalidates a delayed exit even across source automations.
        calls.clear();player("playing",features=2177)
        leave=asyncio.create_task(fire(pause=True))
        await asyncio.sleep(.05)
        hass.states.async_set("automation.newer_gateway_source","on",{"id":"beoremote_source_"+"d"*20,"last_triggered":datetime.now(UTC)})
        await leave
        assert not calls
        hass.states.async_remove("automation.newer_gateway_source")
        checks.append("newer_source_selection_suppresses_delayed_exit")
        # Reselecting this app restarts its automation, cancelling its pending pause.
        calls.clear();player("playing",features=2177)
        leave=asyncio.create_task(fire(pause=True));await asyncio.sleep(.05)
        await fire();await asyncio.gather(leave,return_exceptions=True)
        assert not any(name=="media_player.media_pause" for name,_ in calls)
        assert selected()==["Netflix"]
        checks.append("reselecting_app_cancels_pending_exit_without_pausing_new_playback")
        player()
        fail_launch = True
        calls.clear()
        await fire()
        assert selected() == ["Netflix"] and not any(name == "scene.turn_on" for name, _ in calls)
        fail_launch = False
        checks.append("failed_app_launch_does_not_run_extra_scene_or_retry")

        # A shortened deadline exercises real HA timeout semantics, without 20s per case.
        timed = next(e for e in hass.data["automation"].entities if e.unique_id == short["id"])
        for state, apps in (("unavailable", []), ("idle", ["YouTube"]), ("off", ["Netflix"])):
            calls.clear()
            player(state, apps)
            await fire(target=timed)
            assert not selected() and not any(name == "scene.turn_on" for name, _ in calls)
        player()
        await settle()
        assert not selected()
        checks.append("unreachable_missing_app_and_still_asleep_expire_without_late_action")

        generic_entity = next(e for e in hass.data["automation"].entities if e.unique_id == generic["id"])
        calls.clear()
        hass.states.async_set("media_player.generic", "idle", {"supported_features": 2048, "source_list": ["Game"]})
        await fire(target=generic_entity, source="BGW_abcdefabcdef")
        assert selected() == ["Game"] and len(calls) == 1
        checks.append("generic_device_without_wake_support_opens_without_power_commands")
        checks.append("generated_schema_and_templates_accepted_by_real_core")
        await hass.async_stop()
        print(json.dumps({"checks": checks, "count": len(checks), "real_devices_contacted": False}))


if __name__ == "__main__":
    asyncio.run(main())
