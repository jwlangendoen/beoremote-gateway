import asyncio
import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock

from jinja2 import Environment

from gateway.sources import AdbInventory
from gateway.actions import ActionManager
from gateway.tv_sources import TVSources, automation, automation_id, digest, private_write, validate_entry
from test_actions import FakeHA
from test_gateway import TV
from test_sources import WebSourcesTests


class SourceHA(FakeHA):
    async def states(self):
        return await super().states() + [{"entity_id": "media_player.apple_tv", "state": "idle", "attributes": {
            "friendly_name": "Apple TV", "supported_features": 2048 | 128, "source_list": ["Netflix", "YouTube"]}}]

    async def request(self, method, path, body=None):
        if method == "GET" and path == "config":
            return {"components": ["webhook"]}
        return await super().request(method, path, body)


class FakeADB:
    def __init__(self):
        self.config = {"entries": [], "revision": ""}
        self.operation = ""
        self.calls = []
        self.failure = None

    def status(self):
        catalog = [{"id": "HDMI1", "name": "Console", "source_list": "tv"}, {"id": "HDMI2", "name": "Media player", "source_list": "tv"},
                   {"id": "NATIVE_MUSIC", "name": "Music", "source_list": "music"}, {"id": "NATIVE_RADIO", "name": "Radio", "source_list": "music"}]
        catalog += [{key: e.get(key, "tv") for key in ("id", "name", "source_list")} for e in self.config["entries"]]
        ordered = []
        for group in ("tv", "music"):
            rows = [row for row in catalog if row["source_list"] == group]
            ids = self.config.get("order", {}).get(group, [])
            ordered += [next(row for row in rows if row["id"] == key) for key in ids if any(row["id"] == key for row in rows)]
            ordered += [row for row in rows if row["id"] not in ids]
        return {"tv": TV, "state": "ready", "version": "0.1.3", "source_cancel": True, "source_lists": ["tv", "music"], "source_order": True, "catalog": ordered, "owner": self.config.get("owner", ""),
                "revision": self.config["revision"], "operation": self.operation,
                "entries": [{k: v for k, v in entry.items() if k != "callback"} for entry in self.config["entries"]],
                "slots": [{"slot": n, "free": not any(e["slot"] == n for e in self.config["entries"])} for n in range(8)],
                "inputs": [{"id": "HDMI1", "name": "Console"}, {"id": "HDMI2", "name": "Media player"}],
                "apps": [{"package": "org.example.player", "name": "Player", "system": False}], "legacy_sources": 0}

    async def helper_call(self, address, method, data=None):
        self.calls.append((method, copy.deepcopy(data)))
        if method == "status":
            return self.status()
        if method == "backup":
            return {"config": copy.deepcopy(self.config), "originals": {}}
        if method == "apply":
            if data["expected"] != self.config["revision"]:
                raise ValueError("revision conflict")
            if self.failure == "before":
                self.failure = None
                raise OSError("connection lost")
            self.config = copy.deepcopy(data["config"])
            self.operation = data["operation"]
            if self.failure == "after":
                self.failure = None
                raise OSError("reply lost after commit")
            return {"operation": self.operation}
        if method in {"test", "refresh"}:
            self.operation = data["operation"]
            return {"operation": self.operation}
        raise AssertionError(method)


def source(**changes):
    return {"id": "", "name": "Player", "kind": "app", "target": "org.example.player", "action_kind": "none", "action_target": "", **changes}


class ADBManagementTests(unittest.IsolatedAsyncioTestCase):
    async def test_helper_protocol_has_no_free_commands_or_implicit_source_test(self):
        with tempfile.TemporaryDirectory() as directory:
            adb = AdbInventory(directory)
            adb.port = 12345
            response = base64.b64encode(json.dumps({"state": "ready"}).encode()).decode()
            adb._command = AsyncMock(return_value="Result: Bundle[{result=" + response + "}]")
            self.assertEqual(await adb.helper_call("192.0.2.10", "status"), {"state": "ready"})
            self.assertEqual(adb._command.call_args.args[:5], ("-P", "12345", "-s", "192.0.2.10:5555", "shell"))
            self.assertIn("content://nl.beoremote.tvhelper.control", adb._command.call_args.args)
            with self.assertRaises(ValueError):
                await adb.helper_call("192.0.2.10", "reboot")
            self.assertEqual(adb._command.await_count, 1)

    async def test_installer_uses_only_verified_bundled_apk_and_preserves_data(self):
        with tempfile.TemporaryDirectory() as directory:
            adb = AdbInventory(directory)
            adb.port = 12345
            async def command(*arguments, **kwargs):
                self.assertEqual(arguments[:7], ("-P", "12345", "-s", "192.0.2.10:5555", "install", "-f", "-r"))
                self.assertTrue(Path(arguments[7]).read_bytes().startswith(b"PK"))
                return "Success\n"
            adb._command = AsyncMock(side_effect=command)
            await adb.install_helper("192.0.2.10")
            self.assertEqual(adb._command.await_count, 1)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.status = FakeADB().status()

    def test_only_discovered_apps_and_hdmi_are_accepted(self):
        for changes in ({"target": "other.app"}, {"kind": "hdmi", "target": "HDMI4"}, {"kind": "command", "target": "reboot"}, {"target": []}):
            with self.assertRaises(ValueError):
                validate_entry(source(**changes), self.status)
        self.assertEqual(validate_entry(source(kind="hdmi", target="HDMI1"), self.status)["target"], "HDMI1")

    def test_slots_are_allocated_server_side_and_never_stolen(self):
        self.status["slots"] = [{"slot": 0, "free": False}, {"slot": 1, "free": True}]
        self.assertEqual(validate_entry(source(), self.status)["slot"], 1)
        self.status["slots"][1]["free"] = False
        with self.assertRaises(ValueError):
            validate_entry(source(), self.status)
        with self.assertRaises(ValueError):
            validate_entry({**source(), "slot": 0}, self.status)

    def test_names_and_existing_source_identity_are_bounded(self):
        for changes in ({"name": ""}, {"name": "x" * 33}, {"name": "bad\nname"}, {"id": "ATV_NETFLIX"}):
            with self.assertRaises(ValueError):
                validate_entry(source(**changes), self.status)

    def test_remote_list_and_launch_fields_are_constrained(self):
        self.assertEqual(validate_entry(source(), self.status)["source_list"], "tv")
        self.assertEqual(validate_entry(source(source_list="music"), self.status)["source_list"], "music")
        for changes in ({"source_list": "both"}, {"source_list": []}, {"launch_source": "Netflix"},
                        {"launch_entity": "media_player.apple_tv", "launch_source": "Netflix"},
                        {"kind": "hdmi", "launch_entity": "script.movie", "launch_source": "Netflix"}):
            with self.assertRaises(ValueError):
                validate_entry(source(**changes), self.status)

    def test_music_requires_a_helper_that_supports_it(self):
        self.status.pop("source_lists")
        with self.assertRaisesRegex(ValueError, "Update TV Support"):
            validate_entry(source(source_list="music"), self.status)

    def test_webhook_guard_rejects_stale_other_tv_and_other_source(self):
        entry = source(id="BGW_123456789abc", action_kind="script", action_target="script.movie")
        config = automation(TV, entry, "a" * 64)
        template = Environment().from_string(config["actions"][0]["value_template"])
        valid = {"source": entry["id"], "tv": TV, "created_at": 99}
        def run(data):
            return template.render(trigger={"platform": "webhook", "json": data}, now=lambda: type("Now", (), {"timestamp": lambda _: 100})()) == "True"
        self.assertTrue(run(valid))
        for changes in ({"created_at": 94}, {"created_at": 101}, {"tv": "other"}, {"source": "BGW_abcdefabcdef"}):
            self.assertFalse(run({**valid, **changes}))
        self.assertEqual(config["mode"], "single")
        self.assertTrue(config["triggers"][0]["local_only"])
        self.assertEqual(config["triggers"][0]["allowed_methods"], ["POST"])


class EditorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ha = SourceHA()
        self.editor = TVSources(self.temp.name, ActionManager(self.ha))
        self.adb = FakeADB()

    async def asyncTearDown(self):
        self.temp.cleanup()

    async def save(self, **changes):
        return await self.editor.save(self.adb, "192.0.2.10", "192.0.2.20", TV, self.adb.config["revision"], source(**changes))

    async def test_saving_local_app_registers_without_playback_or_ha_action(self):
        status = await self.save()
        self.assertEqual(len(status["entries"]), 1)
        self.assertFalse(self.ha.configs)
        self.assertFalse(any(method == "test" for method, _ in self.adb.calls))
        self.assertEqual(self.adb.config["entries"][0]["callback"], "")
        self.assertEqual(self.editor.path(TV).stat().st_mode & 0o777, 0o600)
        self.assertTrue(status["can_restore"])

    async def test_music_tv_change_and_restore_reach_native_config(self):
        result = await self.save(source_list="music")
        entry = result["entries"][0]
        self.assertEqual(entry["source_list"], "music")
        self.assertEqual(self.adb.config["entries"][0]["source_list"], "music")
        result = await self.save(id=entry["id"], source_list="tv")
        self.assertEqual(result["entries"][0]["source_list"], "tv")
        restored = await self.editor.restore(self.adb, "192.0.2.10", TV, result["revision"])
        self.assertEqual(restored["entries"][0]["source_list"], "music")
        self.assertFalse(self.ha.configs)

    async def test_reordering_existing_sources_is_separate_per_list_and_has_no_actions(self):
        result = await self.editor.reorder(self.adb, "192.0.2.10", TV, "", "tv", ["HDMI2", "HDMI1"])
        self.assertEqual([r["id"] for r in result["catalog"] if r["source_list"] == "tv"], ["HDMI2", "HDMI1"])
        self.assertEqual([r["id"] for r in result["catalog"] if r["source_list"] == "music"], ["NATIVE_MUSIC", "NATIVE_RADIO"])
        self.assertEqual(self.adb.config["entries"], [])
        self.assertFalse(self.ha.calls)
        self.assertFalse(any(method == "test" for method, _ in self.adb.calls))
        apply = next(data for method, data in self.adb.calls if method == "apply")
        self.assertEqual(apply["order_check"], {"source_list": "tv", "ids": ["HDMI2", "HDMI1"]})
        restored = await self.editor.restore(self.adb, "192.0.2.10", TV, result["revision"])
        self.assertEqual([r["id"] for r in restored["catalog"] if r["source_list"] == "tv"], ["HDMI1", "HDMI2"])
        self.assertFalse(self.ha.calls)

    async def test_ordering_keeps_shortcut_routes_custom_actions_and_paused_state(self):
        result = await self.save(action_kind="script", action_target="script.movie")
        row = result["entries"][0];key = automation_id(TV, row["id"])
        self.ha.configs[key]["description"] = "Custom user work"
        self.ha.enabled[key] = False
        before = copy.deepcopy(self.ha.configs), copy.deepcopy(self.editor.load(TV)), copy.deepcopy(self.adb.config["entries"])
        self.ha.calls.clear()
        ordered = await self.editor.reorder(self.adb, "192.0.2.10", TV, result["revision"], "tv", [row["id"], "HDMI1", "HDMI2"])
        self.assertEqual((self.ha.configs, self.editor.load(TV), self.adb.config["entries"]), before)
        await self.editor.restore(self.adb, "192.0.2.10", TV, ordered["revision"])
        self.assertFalse(self.ha.calls)
        self.assertFalse(self.ha.enabled[key])

    async def test_bad_or_stale_order_cannot_change_sources(self):
        for group, ids in (("tv", ["HDMI1"]), ("tv", ["HDMI1", "HDMI1"]), ("tv", ["HDMI1", "FOREIGN"]),
                           ("tv", ["NATIVE_MUSIC", "NATIVE_RADIO"]), ("both", []), ("tv", [None]), ([], [])):
            with self.assertRaises(ValueError):
                await self.editor.reorder(self.adb, "192.0.2.10", TV, "", group, ids)
        with self.assertRaisesRegex(ValueError, "changed"):
            await self.editor.reorder(self.adb, "192.0.2.10", TV, "a" * 32, "tv", ["HDMI2", "HDMI1"])
        self.assertFalse(any(method == "apply" for method, _ in self.adb.calls))
        self.assertFalse(self.editor.path(TV, True).exists())

    async def test_ordering_requires_capable_helper_and_noop_is_not_written(self):
        await self.editor.reorder(self.adb, "192.0.2.10", TV, "", "tv", ["HDMI1", "HDMI2"])
        self.assertFalse(self.editor.path(TV, True).exists())
        self.assertFalse(any(method == "apply" for method, _ in self.adb.calls))
        original_status = self.adb.status
        self.adb.status = lambda: {**original_status(), "source_order": False}
        with self.assertRaisesRegex(ValueError, "Update TV Support"):
            await self.editor.reorder(self.adb, "192.0.2.10", TV, "", "tv", ["HDMI2", "HDMI1"])

    async def test_helper_update_waits_for_the_new_version_instead_of_cached_ready(self):
        self.editor.status = AsyncMock(side_effect=[{"state": "ready", "version": "0.1.1"}, {"state": "ready", "version": "0.1.2"}])
        status = await self.editor.wait_ready(self.adb, "192.0.2.10", TV, version="0.1.2")
        self.assertEqual(status["version"], "0.1.2")
        self.assertEqual(self.editor.status.await_count, 2)

    async def test_previous_ordering_helper_must_be_retired_before_native_reordering(self):
        original = self.adb.status
        self.adb.status = lambda: {**original(), "legacy_sources": 8}
        with self.assertRaisesRegex(ValueError, "previous source helper"):
            await self.editor.reorder(self.adb, "192.0.2.10", TV, "", "tv", ["HDMI2", "HDMI1"])
        self.assertFalse(any(method == "apply" for method, _ in self.adb.calls))

    async def test_uncertain_order_reply_is_reconciled_or_can_be_restored(self):
        self.adb.failure = "after"
        result = await self.editor.reorder(self.adb, "192.0.2.10", TV, "", "tv", ["HDMI2", "HDMI1"])
        self.assertEqual(self.adb.config["order"]["tv"], ["HDMI2", "HDMI1"])
        await self.editor.restore(self.adb, "192.0.2.10", TV, result["revision"])
        self.adb.failure = "before"
        with self.assertRaisesRegex(ValueError, "not confirmed"):
            await self.editor.reorder(self.adb, "192.0.2.10", TV, self.adb.config["revision"], "music", ["NATIVE_RADIO", "NATIVE_MUSIC"])
        await self.editor.restore(self.adb, "192.0.2.10", TV, self.adb.config["revision"])
        self.assertFalse(self.ha.calls)

    async def test_native_order_refusal_keeps_its_actionable_message(self):
        original = self.adb.helper_call
        async def refuse(address, method, data=None):
            if method == "apply":
                raise ValueError("Switch to another source, then refresh sources before moving the source that is playing.")
            return await original(address, method, data)
        self.adb.helper_call = refuse
        with self.assertRaisesRegex(ValueError, "Switch to another source"):
            await self.editor.reorder(self.adb, "192.0.2.10", TV, "", "tv", ["HDMI2", "HDMI1"])
        self.assertNotIn("order", self.adb.config)

    async def test_source_save_and_removal_keep_the_saved_order(self):
        await self.editor.reorder(self.adb, "192.0.2.10", TV, "", "tv", ["HDMI2", "HDMI1"])
        result = await self.save()
        self.assertEqual(self.adb.config["order"]["tv"], ["HDMI2", "HDMI1"])
        await self.editor.remove(self.adb, "192.0.2.10", TV, result["revision"], result["entries"][0]["id"])
        self.assertEqual(self.adb.config["order"]["tv"], ["HDMI2", "HDMI1"])

    async def test_connected_app_saves_without_launch_and_runs_before_extra_action(self):
        result = await self.save(kind="hdmi", target="HDMI2", launch_entity="media_player.apple_tv",
                                 launch_source="Netflix", action_kind="scene", action_target="scene.movie")
        row = result["entries"][0]
        config = self.ha.configs[automation_id(TV, row["id"])]
        actions = config["actions"]
        self.assertEqual(actions[-2], {"action": "media_player.select_source", "target": {"entity_id": "media_player.apple_tv"}, "data": {"source": "Netflix"}})
        self.assertEqual(actions[-1]["action"], "scene.turn_on")
        self.assertEqual(config["mode"], "restart")
        self.assertEqual(config["conditions"], [actions[0]])  # Invalid webhooks cannot cancel a valid run.
        self.assertTrue(self.adb.config["entries"][0]["cancel_launch"])
        self.assertFalse(any(path.startswith("services/media_player/") or path == "services/scene/turn_on" for _, path, _ in self.ha.calls))
        self.assertFalse(any(method == "test" for method, _ in self.adb.calls))
        self.assertNotIn("launch_entity", self.adb.config["entries"][0])
        self.assertEqual(row["launch_source"], "Netflix")
        self.assertNotIn("callback", row)

    async def test_connected_app_alone_still_creates_automation_and_edit_preserves_pause(self):
        result = await self.save(kind="hdmi", target="HDMI2", launch_entity="media_player.apple_tv", launch_source="Netflix")
        row = result["entries"][0]; key = automation_id(TV, row["id"])
        self.assertEqual(self.ha.configs[key]["actions"][-1]["data"], {"source": "Netflix"})
        self.ha.enabled[key] = False
        await self.save(id=row["id"], kind="hdmi", target="HDMI2", launch_entity="media_player.apple_tv", launch_source="YouTube")
        self.assertFalse(self.ha.enabled[key])
        self.assertEqual(self.ha.configs[key]["actions"][-1]["data"], {"source": "YouTube"})

    async def test_connected_app_requires_live_discovered_choice_before_any_write(self):
        for changes in ({"launch_entity": "media_player.other", "launch_source": "Netflix"},
                        {"launch_entity": "media_player.apple_tv", "launch_source": "Unknown app"}):
            with self.assertRaisesRegex(ValueError, "unavailable"):
                await self.save(kind="hdmi", target="HDMI2", **changes)
        self.assertFalse(self.ha.configs)
        self.assertFalse(self.adb.config["entries"])

    async def test_connected_app_requires_helper_cancellation_support_before_writes(self):
        original = self.adb.status
        self.adb.status = lambda: {**original(), "source_cancel": False}
        with self.assertRaisesRegex(ValueError, "Update TV Support"):
            await self.save(kind="hdmi", target="HDMI2", launch_entity="media_player.apple_tv", launch_source="Netflix")
        self.assertFalse(self.ha.configs)
        self.assertFalse(self.adb.config["entries"])

    async def test_resaving_unchanged_old_launch_upgrades_it_but_keeps_pause(self):
        result = await self.save(kind="hdmi", target="HDMI2", launch_entity="media_player.apple_tv", launch_source="Netflix")
        row = result["entries"][0]; key = automation_id(TV, row["id"])
        old = copy.deepcopy(self.ha.configs[key]); old["mode"] = "single"
        self.ha.configs[key] = old; self.ha.enabled[key] = False
        store = self.editor.load(TV); store["entries"][0]["action_hash"] = digest(old)
        store["entries"][0].pop("launch_cancel", None)
        private_write(self.editor.path(TV), store)
        await self.save(id=row["id"], kind="hdmi", target="HDMI2", launch_entity="media_player.apple_tv", launch_source="Netflix")
        self.assertEqual(self.ha.configs[key]["mode"], "restart")
        self.assertFalse(self.ha.enabled[key])
        self.assertTrue(self.adb.config["entries"][0]["cancel_launch"])

    async def test_resaving_customized_old_launch_does_not_rewrite_or_enable_cancellation(self):
        result = await self.save(kind="hdmi", target="HDMI2", launch_entity="media_player.apple_tv", launch_source="Netflix")
        row = result["entries"][0]; key = automation_id(TV, row["id"])
        store = self.editor.load(TV); store["entries"][0].pop("launch_cancel", None)
        private_write(self.editor.path(TV), store)
        self.ha.configs[key]["description"] = "My custom action"
        before = copy.deepcopy(self.ha.configs[key])
        await self.save(id=row["id"], kind="hdmi", target="HDMI2", launch_entity="media_player.apple_tv", launch_source="Netflix")
        self.assertEqual(self.ha.configs[key], before)
        self.assertFalse(self.adb.config["entries"][0]["cancel_launch"])

    async def test_media_choices_filter_capabilities_and_unavailable_and_keep_generic_devices(self):
        original_states = self.ha.states
        extras = [
            {"entity_id": "media_player.console", "state": "idle", "attributes": {"friendly_name": "Console", "supported_features": 2048, "source_list": ["Game", "Game", "bad\nvalue"]}},
            {"entity_id": "media_player.offline", "state": "unavailable", "attributes": {"supported_features": 2048, "source_list": ["App"]}},
            {"entity_id": "media_player.no_support", "state": "idle", "attributes": {"supported_features": 0, "source_list": ["App"]}}]
        async def all_states():
            return await original_states() + extras
        self.ha.states = all_states
        players = await self.editor.media_players()
        self.assertEqual([p["id"] for p in players], ["media_player.apple_tv", "media_player.console"])
        self.assertEqual(players[1]["sources"], [{"id": "Game", "name": "Game"}])
        result = await self.save(kind="hdmi", target="HDMI1", launch_entity="media_player.console", launch_source="Game")
        actions = self.ha.configs[automation_id(TV, result["entries"][0]["id"])]["actions"]
        self.assertNotIn('media_player.turn_on', json.dumps(actions))  # No unsupported wake action.

    async def test_script_uses_limited_webhook_without_exposing_it_to_browser(self):
        result = await self.save(kind="hdmi", target="HDMI2", action_kind="script", action_target="script.movie")
        private = self.editor.load(TV)["entries"][0]
        key = automation_id(TV, private["id"])
        self.assertEqual(self.ha.configs[key]["actions"][1]["action"], "script.turn_on")
        self.assertNotIn(private["webhook"], json.dumps(result))
        self.assertNotIn("callback", result["entries"][0])
        self.assertTrue(result["entries"][0]["edit_path"].endswith(key))
        self.assertFalse(any(path.startswith("services/script/") for _, path, _ in self.ha.calls))

    async def test_missing_webhook_integration_does_not_create_an_unusable_source(self):
        self.editor.actions.ha = FakeHA()
        with self.assertRaisesRegex(ValueError, "webhook integration"):
            await self.save(action_kind="script", action_target="script.movie")
        self.assertFalse(self.adb.config["entries"])
        self.assertFalse(any(method == "apply" for method, _ in self.adb.calls))

    async def test_custom_action_creates_empty_native_ha_editor(self):
        result = await self.save(action_kind="custom")
        config = next(iter(self.ha.configs.values()))
        self.assertEqual(len(config["actions"]), 1)
        self.assertIn("edit_path", result["entries"][0])

    async def test_no_free_slot_is_rejected_before_any_automation_write(self):
        for _ in range(8):
            await self.save()
        before = len(self.ha.calls)
        with self.assertRaisesRegex(ValueError, "no free source slot"):
            await self.save(action_kind="script", action_target="script.movie")
        self.assertEqual(len(self.ha.calls), before)
        self.assertEqual(len(self.adb.config["entries"]), 8)

    async def test_stale_revision_is_rejected_before_changes(self):
        await self.save()
        before = copy.deepcopy(self.adb.config)
        with self.assertRaises(ValueError):
            await self.editor.save(self.adb, "192.0.2.10", "192.0.2.20", TV, "", source())
        self.assertEqual(self.adb.config, before)

    async def test_foreign_gateway_and_tv_are_refused(self):
        self.adb.config["owner"] = "b" * 32
        with self.assertRaisesRegex(ValueError, "another gateway"):
            await self.editor.status(self.adb, "192.0.2.10", TV)
        self.adb.config.pop("owner")
        with self.assertRaisesRegex(ValueError, "different TV"):
            await self.editor.status(self.adb, "192.0.2.10", "other")

    async def test_save_failure_keeps_recoverable_backup_and_never_tests(self):
        self.adb.failure = "before"
        with self.assertRaisesRegex(ValueError, "not confirmed"):
            await self.save(action_kind="script", action_target="script.movie")
        self.assertEqual(self.adb.config["entries"], [])
        self.assertTrue(self.editor.path(TV, True).exists())
        # Keep an uncertain capability until explicit recovery, rather than guessing
        # whether the TV applied a change whose reply was lost.
        self.assertTrue(self.ha.configs)
        await self.editor.restore(self.adb, "192.0.2.10", TV, "")
        self.assertFalse(self.ha.configs)
        self.assertFalse(any(method == "test" for method, _ in self.adb.calls))

    async def test_lost_reply_after_commit_is_reconciled_without_deleting_action(self):
        self.adb.failure = "after"
        result = await self.save(action_kind="script", action_target="script.movie")
        self.assertEqual(len(result["entries"]), 1)
        self.assertTrue(self.ha.configs)
        self.assertEqual(len(self.editor.load(TV)["entries"]), 1)

    async def test_edited_ha_action_is_preserved_but_not_overwritten(self):
        result = await self.save(action_kind="script", action_target="script.movie")
        row = result["entries"][0]
        key = automation_id(TV, row["id"])
        self.ha.configs[key]["description"] = "User edited in HA"
        with self.assertRaisesRegex(ValueError, "edited in Home Assistant"):
            await self.save(id=row["id"], action_kind="scene", action_target="scene.movie")
        await self.save(id=row["id"], name="New label", action_kind="script", action_target="script.movie")
        self.assertEqual(self.ha.configs[key]["description"], "User edited in HA")

    async def test_edit_preserves_a_paused_ha_automation(self):
        result = await self.save(action_kind="script", action_target="script.movie")
        row = result["entries"][0]
        key = automation_id(TV, row["id"])
        self.ha.enabled[key] = False
        await self.save(id=row["id"], action_kind="scene", action_target="scene.movie")
        self.assertFalse(self.ha.enabled[key])

    async def test_remove_customized_automation_keeps_user_work(self):
        result = await self.save(action_kind="custom")
        row = result["entries"][0]
        key = automation_id(TV, row["id"])
        self.ha.configs[key]["description"] = "User work"
        await self.editor.remove(self.adb, "192.0.2.10", TV, self.adb.config["revision"], row["id"])
        self.assertIn(key, self.ha.configs)
        self.assertEqual(self.adb.config["entries"], [])

    async def test_restore_recovers_both_source_and_action_configuration(self):
        result = await self.save(action_kind="script", action_target="script.movie")
        row = result["entries"][0]
        original = copy.deepcopy(self.ha.configs)
        await self.save(id=row["id"], name="Other", action_kind="scene", action_target="scene.movie")
        restored = await self.editor.restore(self.adb, "192.0.2.10", TV, self.adb.config["revision"])
        self.assertEqual(restored["entries"][0]["name"], "Player")
        self.assertEqual(self.ha.configs, original)

    async def test_restore_refuses_new_user_edits_in_ha(self):
        await self.save(action_kind="script", action_target="script.movie")
        key = next(iter(self.ha.configs))
        self.ha.configs[key]["description"] = "New user edit"
        with self.assertRaisesRegex(ValueError, "changed in Home Assistant"):
            await self.editor.restore(self.adb, "192.0.2.10", TV, self.adb.config["revision"])

    async def test_test_is_explicit_and_only_for_a_saved_source(self):
        with self.assertRaises(ValueError):
            await self.editor.test(self.adb, "192.0.2.10", TV, "BGW_123456789abc")
        result = await self.save()
        self.assertEqual(await self.editor.test(self.adb, "192.0.2.10", TV, result["entries"][0]["id"]), {"sent": True})
        self.assertEqual([method for method, _ in self.adb.calls].count("test"), 1)


class EditorWebTests(WebSourcesTests):
    async def test_new_operations_require_current_admin_and_page_token(self):
        self.controller.source_operation = AsyncMock(return_value={"ok": True})
        bodies = {"install": {"retire_old": False}, "refresh": {}, "targets": {}, "save": {"revision": "", "entry": {}},
                  "remove": {"revision": "", "id": "BGW_123456789abc"}, "restore": {"revision": ""}, "test": {"id": "BGW_123456789abc"},
                  "reorder": {"revision": "", "source_list": "tv", "ids": ["HDMI2", "HDMI1"]}}
        for operation, body in bodies.items():
            response = await self.client.post("/api/sources/" + operation, json=body)
            self.assertEqual(response.status, 403)
        self.admin.return_value = False
        response = await self.client.post("/api/sources/install", json={"tv_jid": TV, **bodies["install"]}, headers=self.headers)
        self.assertEqual(response.status, 403)
        self.controller.source_operation.assert_not_awaited()
        self.admin.return_value = True
        for operation, body in bodies.items():
            response = await self.client.post("/api/sources/" + operation, json={"tv_jid": TV, **body}, headers=self.headers)
            self.assertEqual(response.status, 200)

    async def test_stale_tv_page_cannot_install_or_replace_a_helper(self):
        await self.controller.scan()
        await self.controller.select(TV)
        await self.controller.set_sources_enabled(True)
        with self.assertRaisesRegex(ValueError, "selected TV changed"):
            await self.controller.source_operation("install", {"tv_jid": "other", "retire_old": True})
        self.adb.install_helper.assert_not_awaited()
        self.adb.retire_legacy.assert_not_awaited()
        with self.assertRaisesRegex(ValueError, "selected TV changed"):
            await self.controller.source_operation("reorder", {"tv_jid": "other", "revision": "", "source_list": "tv", "ids": []})

    async def test_unscoped_commands_and_malformed_inputs_are_rejected(self):
        self.controller.source_operation = AsyncMock()
        for operation, body in (("shell", {}), ("install", {"retire_old": "true"}), ("test", {"id": "other"}), ("restore", {"revision": []}), ("save", {"revision": "", "entry": []})):
            response = await self.client.post("/api/sources/" + operation, json={"tv_jid": TV, **body}, headers=self.headers)
            self.assertEqual(response.status, 400)
        self.controller.source_operation.assert_not_awaited()
