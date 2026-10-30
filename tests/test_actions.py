import copy
import json
import unittest
from unittest.mock import Mock, patch

from aiohttp import web
from aiohttp.test_utils import TestServer
from jinja2 import Environment

from gateway.actions import ActionManager, FRESH, make_rule, owned_rule, rule_id
from gateway.config import Options
from gateway.ha import HAError, HomeAssistant
from gateway.learning import ButtonLearning
from gateway.runtime import GatewayRuntime
from test_gateway import TV
import test_setup

PRESS = {"peer_jid": TV, "originator": "0", "data_hex": "001b00000f0000000000000000"}
RELEASE = {**PRESS, "data_hex": "001b00007e0000000000000000"}
OTHER = TV.replace("12345678", "87654321")


class FakeHA:
    def __init__(self):
        self.configs, self.calls, self.enabled = {}, [], {}
        self.scene = {"entity_id": "scene.movie", "state": "scening",
                      "attributes": {"friendly_name": "Movie time"}}

    async def states(self):
        return [self.scene, {"entity_id": "light.living_room", "state": "on",
                            "attributes": {"friendly_name": "Living room"}},
                {"entity_id": "light.offline", "state": "unavailable"}] + [
                    {"entity_id": "automation.test_" + key, "state": "on" if self.enabled.get(key, True) else "off",
                     "attributes": {"id": key}} for key in self.configs]

    async def request(self, method, path, body=None):
        self.calls.append((method, path, copy.deepcopy(body)))
        if path.startswith("config/automation/config/"):
            key = path.rsplit("/", 1)[-1]
            if method == "GET":
                return copy.deepcopy(self.configs.get(key))
            if method == "POST":
                self.configs[key] = copy.deepcopy(body)
            if method == "DELETE":
                del self.configs[key]
        if path in ("services/automation/turn_on", "services/automation/turn_off"):
            self.enabled[body["entity_id"].removeprefix("automation.test_")] = path.endswith("turn_on")
        return {"result": "ok"}


class LearningTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.learn = ButtonLearning(clock=lambda: self.now)

    def test_learns_only_light_from_selected_tv_and_consumes_hold_until_release(self):
        session = self.learn.start(TV)
        self.assertTrue(self.learn.observe({**PRESS, "peer_jid": OTHER}))
        self.assertFalse(self.learn.observe({**PRESS, "originator": "1"}))
        self.assertEqual(self.learn.status()["state"], "listening")
        self.assertFalse(self.learn.observe(RELEASE))
        self.assertEqual(self.learn.status()["state"], "listening")
        self.assertFalse(self.learn.observe(PRESS))
        self.assertEqual(self.learn.status()["button_name"], "LIGHT function 1")
        self.assertEqual(self.learn.capture(session["id"], TV), PRESS)
        self.learn.finish()
        self.assertFalse(self.learn.observe(PRESS))
        self.assertFalse(self.learn.observe(RELEASE))
        self.assertTrue(self.learn.observe(PRESS))

    def test_timeout_cancel_and_wrong_session_cannot_save(self):
        session = self.learn.start(TV)
        self.now = 31
        self.assertEqual(self.learn.status(), {"state": "idle"})
        for key, jid in ((session["id"], TV), ([], TV), ("unknown", OTHER)):
            with self.assertRaises(ValueError):
                self.learn.capture(key, jid)
        session = self.learn.start(TV)
        self.learn.observe(PRESS)
        self.now += 301
        with self.assertRaises(ValueError):
            self.learn.capture(session["id"], TV)
        self.assertTrue(self.learn.observe(PRESS))

    def test_runtime_does_not_publish_learning_press_but_next_press_is_normal(self):
        runtime = GatewayRuntime(Options())
        runtime.buttons.clock = lambda: self.now
        runtime.publisher = Mock()
        runtime.observer = self.learn.observe
        self.learn.start(TV)
        runtime.telegram(PRESS)
        runtime.publisher.submit.assert_not_called()
        self.learn.finish()
        runtime.telegram(RELEASE)
        self.now = 0.2
        runtime.telegram(PRESS)
        runtime.publisher.submit.assert_called_once_with(PRESS)
        runtime.telegram(PRESS)
        runtime.publisher.submit.assert_called_once()

    def test_newly_learned_light_commands_also_suppress_hold_repeats(self):
        runtime = GatewayRuntime(Options())
        runtime.publisher = Mock()
        event = {**PRESS, "data_hex": "001b0000050000000000000000"}
        runtime.telegram(event)
        runtime.telegram(event)
        runtime.publisher.submit.assert_called_once_with(event)

    def test_suppressed_learning_release_still_clears_previous_hold(self):
        runtime = GatewayRuntime(Options())
        runtime.buttons.clock = lambda: self.now
        runtime.publisher = Mock()
        runtime.observer = self.learn.observe
        runtime.telegram(PRESS)
        self.now = 0.2
        self.learn.start(TV)
        runtime.telegram(RELEASE)
        runtime.telegram(PRESS)
        self.learn.finish()
        runtime.telegram(RELEASE)
        self.now = 0.4
        runtime.telegram(PRESS)
        self.assertEqual(runtime.publisher.submit.call_count, 2)

    def test_generated_action_cannot_run_without_a_fresh_real_event(self):
        env = Environment()
        env.filters["float"] = lambda value, default=0: float(value or default)
        template = env.from_string(FRESH)
        now = Mock()
        now.timestamp.return_value = 100
        for received, expected in ((99.5, True), (95, False), (105, False), (0, False)):
            trigger = {"platform": "event", "event": {"data": {"received_at": received}}}
            self.assertEqual(template.render(now=lambda: now, trigger=trigger), str(expected))
        self.assertEqual(template.render(now=lambda: now), "False")
        self.assertEqual(template.render(now=lambda: now, trigger={"platform": "manual"}), "False")


class ActionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.ha = FakeHA()
        self.manager = ActionManager(self.ha)

    async def test_save_is_native_idempotent_and_never_runs_the_scene(self):
        saved = await self.manager.save(PRESS, "Movie", "scene", "scene.movie")
        key = saved["id"]
        self.assertEqual(self.ha.configs[key]["triggers"][0]["event_data"], PRESS)
        self.assertNotIn("initial_state", self.ha.configs[key])
        await self.manager.save(PRESS, "Movie", "scene", "scene.movie")
        writes = [call for call in self.ha.calls if call[:2] == ("POST", "config/automation/config/" + key)]
        self.assertEqual(len(writes), 1)
        self.assertFalse(any(path in ("services/scene/turn_on", "services/light/turn_off", "services/automation/trigger") for _, path, _ in self.ha.calls))
        self.assertTrue(self.ha.enabled[key])
        rows = await self.manager.list(TV)
        self.assertEqual(rows[0]["target_name"], "Movie time")
        self.assertEqual(await self.manager.list(OTHER), [])

    async def test_change_pause_enable_remove_own_rule_only(self):
        key = (await self.manager.save(PRESS, "Movie", "scene", "scene.movie"))["id"]
        await self.manager.update(key, TV, "All off", "light_off", "light.living_room")
        self.assertEqual(self.ha.configs[key]["actions"][1]["action"], "light.turn_off")
        await self.manager.toggle(key, TV, False)
        self.assertFalse(self.ha.enabled[key])
        await self.manager.toggle(key, TV, True)
        with self.assertRaises(ValueError):
            await self.manager.remove(key, OTHER)
        with self.assertRaises(ValueError):
            await self.manager.toggle(key, TV, "false")
        await self.manager.remove(key, TV)
        self.assertNotIn(key, self.ha.configs)
        mutations = [call for call in self.ha.calls if call[0] != "GET"]
        self.assertEqual(mutations[-2][1], "services/automation/turn_off")
        self.assertEqual(mutations[-1][0], "DELETE")

    async def test_customized_and_unrelated_automations_are_preserved(self):
        key = (await self.manager.save(PRESS, "Movie", "scene", "scene.movie"))["id"]
        self.ha.configs[key]["actions"] = [{"action": "script.my_custom_action"}]
        self.assertTrue((await self.manager.list(TV))[0]["customized"])
        before = copy.deepcopy(self.ha.configs)
        for operation in (self.manager.save(PRESS, "Other", "scene", "scene.movie"),
                          self.manager.update(key, TV, "Other", "scene", "scene.movie"),
                          self.manager.toggle(key, TV, False), self.manager.remove(key, TV),
                          self.manager.remove("someone_elses_rule", TV)):
            with self.assertRaises(ValueError):
                await operation
        self.assertEqual(self.ha.configs, before)
        self.ha.configs[key]["description"] = "My existing rule"
        self.assertEqual(await self.manager.list(TV), [])

    async def test_missing_wrong_domain_and_arbitrary_targets_are_rejected_without_writes(self):
        for kind, target in (("scene", "scene.missing"), ("scene", "light.living_room"),
                             ("light_off", "light.offline"), ("scene", "../config"),
                             ("script", "script.arbitrary")):
            with self.assertRaises(ValueError):
                await self.manager.save(PRESS, "Movie", kind, target)
        self.assertTrue(all(method == "GET" for method, _, _ in self.ha.calls))
        self.assertNotEqual(rule_id(PRESS), rule_id({**PRESS, "peer_jid": OTHER}))


class HAClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_contract_errors_and_credentials_stay_private(self):
        seen = []
        async def endpoint(request):
            seen.append((request.path, request.headers.get("Authorization")))
            if request.path == "/states":
                return web.json_response([])
            if request.path == "/missing":
                return web.Response(status=404)
            if request.path == "/redirect":
                raise web.HTTPFound("/states")
            return web.Response(status=500, text="sensitive fixture response")
        app = web.Application()
        app.router.add_route("*", "/{path:.*}", endpoint)
        async with TestServer(app) as server:
            with patch("gateway.ha.BASE", str(server.make_url("/"))):
                ha = HomeAssistant("synthetic-test-token")
                self.assertEqual(await ha.states(), [])
                self.assertIsNone(await ha.request("GET", "missing"))
                for path, expected_status in (("redirect", 302), ("failure", 500)):
                    with self.assertRaises(HAError) as error:
                        await ha.request("GET", path)
                    self.assertEqual(error.exception.status, expected_status)
                    self.assertNotIn("sensitive", str(error.exception))
        self.assertEqual(len([path for path, _ in seen if path == "/states"]), 1)
        self.assertTrue(all(auth == "Bearer synthetic-test-token" for _, auth in seen))


class ActionWebTests(test_setup.SetupWebTests):
    async def test_learn_save_edit_and_manage_through_ingress(self):
        self.controller.actions = ActionManager(FakeHA())
        await self.controller.scan()
        await self.controller.select(TV)
        async def post(path, body):
            response = await self.client.post(path, json=body, headers=self.headers)
            self.assertEqual(response.status, 200, await response.text())
            return await response.json()
        learned = await post("/api/learning/start", {})
        self.assertFalse(self.controller.runtime.observer(PRESS))
        status = await (await self.client.get("/api/status")).json()
        self.assertEqual(status["learning"]["state"], "captured")
        self.assertNotIn("data_hex", status["learning"])
        saved = await post("/api/actions/save", {"session_id": learned["id"], "name": "Movie", "kind": "scene", "target": "scene.movie"})
        self.assertEqual(self.controller.learning.status()["state"], "idle")
        await post("/api/actions/update", {"id": saved["id"], "name": "All off", "kind": "light_off", "target": "light.living_room"})
        await post("/api/actions/toggle", {"id": saved["id"], "enabled": False})
        rows = await (await self.client.get("/api/actions")).json()
        self.assertFalse(rows["actions"][0]["enabled"])
        await post("/api/actions/remove", {"id": saved["id"]})
        self.assertEqual((await (await self.client.get("/api/actions")).json())["actions"], [])

    async def test_csrf_required_and_saved_session_cannot_be_reused_after_tv_change(self):
        self.controller.actions = ActionManager(FakeHA())
        await self.controller.scan()
        await self.controller.select(TV)
        learned = await self.controller.start_learning()
        self.controller.runtime.observer(PRESS)
        await self.controller.select(OTHER)
        response = await self.client.post("/api/actions/save", headers=self.headers, json={
            "session_id": learned["id"], "name": "Movie", "kind": "scene", "target": "scene.movie"})
        self.assertEqual(response.status, 400)
        for path in ("learning/start", "learning/cancel", "actions/save", "actions/update", "actions/toggle", "actions/remove"):
            response = await self.client.post("/api/" + path, json={})
            self.assertEqual(response.status, 403)
        self.assertEqual(self.controller.actions.ha.configs, {})
