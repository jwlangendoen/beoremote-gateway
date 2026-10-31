import asyncio
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from aiohttp.test_utils import TestClient, TestServer

from gateway.config import Options
from gateway.sources import AdbInventory, SourceError, SourceSettings, matches_tv, packages
from gateway.web import make_app
from test_setup import SetupFixture, device
from test_gateway import TV as TV_JID

TV = {"address": "192.0.2.10"}


class AdbTests(unittest.IsolatedAsyncioTestCase):
    async def test_authorization_required_does_not_run_shell_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            adb = AdbInventory(directory)
            adb.port = 12345
            adb._command = AsyncMock(side_effect=["connected", "List of devices attached\n192.0.2.10:5555\tunauthorized\n"])
            self.assertEqual(await adb.inspect(TV["address"]), {"state": "authorization_required", "apps": []})
            self.assertEqual(adb._command.await_count, 2)

    async def test_connect_timeout_still_reports_pending_tv_authorization(self):
        with tempfile.TemporaryDirectory() as directory:
            adb = AdbInventory(directory)
            adb.port = 12345
            adb._command = AsyncMock(side_effect=[SourceError("adb_timeout"),
                                                  "192.0.2.10:5555\tunauthorized\n"])
            self.assertEqual((await adb.inspect(TV["address"]))["state"], "authorization_required")
            self.assertEqual(adb._command.await_count, 2)

    async def test_only_selected_device_and_fixed_inventory_commands_are_used(self):
        with tempfile.TemporaryDirectory() as directory:
            adb = AdbInventory(directory)
            adb.port = 12345
            adb._command = AsyncMock(side_effect=["connected", "192.0.2.10:5555\tdevice\nother:5555\tdevice\n",
                                                   "QM153E\n", "5.1.1\n", "package:org.example.player\n", ""])
            result = await adb.inspect(TV["address"])
            self.assertEqual(result["state"], "connected")
            self.assertEqual(result["model"], "QM153E")
            self.assertEqual(result["apps"][0]["package"], "org.example.player")
            for call in adb._command.call_args_list[2:]:
                self.assertEqual(call.args[:5], ("-P", "12345", "-s", "192.0.2.10:5555", "shell"))
            self.assertEqual([call.args[5:] for call in adb._command.call_args_list[2:]], [
                ("getprop", "ro.product.model"), ("getprop", "ro.build.version.release"),
                ("pm", "list", "packages"), ("pm", "list", "packages", "-s")])

    async def test_unreachable_device_never_reads_another_connected_tv(self):
        with tempfile.TemporaryDirectory() as directory:
            adb = AdbInventory(directory)
            adb.port = 12345
            adb._command = AsyncMock(side_effect=["failed to connect", "192.0.2.20:5555\tdevice\n"])
            self.assertEqual((await adb.inspect(TV["address"]))["state"], "unreachable")
            self.assertEqual(adb._command.await_count, 2)

    async def test_missing_client_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as directory:
            adb = AdbInventory(directory, binary="/nonexistent-gateway-adb")
            with self.assertRaises(SourceError) as error:
                await adb._command("version")
            self.assertEqual(error.exception.code, "adb_unavailable")

    async def test_timed_out_subprocess_is_killed_without_exposing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            adb = AdbInventory(directory)
            process = AsyncMock()
            process.returncode = None
            process.kill = unittest.mock.Mock()
            process.stdout.read = AsyncMock(side_effect=asyncio.TimeoutError)
            with patch("asyncio.create_subprocess_exec", return_value=process):
                with self.assertRaises(SourceError) as error:
                    await adb._command("devices")
            self.assertEqual(error.exception.code, "adb_timeout")
            process.kill.assert_called_once()
            process.wait.assert_awaited_once()


class PreferenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_optional_extension_is_persistent_and_never_connects_on_enable(self):
        with tempfile.TemporaryDirectory() as directory:
            adb = AsyncMock()
            settings = SourceSettings(directory, adb=adb)
            self.assertFalse(settings.enabled)
            await settings.set_enabled(True)
            self.assertTrue(SourceSettings(directory).enabled)
            self.assertEqual(settings.path.stat().st_mode & 0o777, 0o600)
            adb.inspect.assert_not_called()
            await settings.set_enabled(False)
            adb.close.assert_awaited_once()
            self.assertFalse(SourceSettings(directory).enabled)

    async def test_bad_preferences_do_not_prevent_the_gateway_from_starting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source-management.json"
            for data in ('invalid', '[]', '{"enabled":"yes"}'):
                path.write_text(data)
                settings = SourceSettings(directory)
                self.assertFalse(settings.enabled)
                self.assertTrue(settings.error)

    async def test_writes_do_not_follow_predictable_temporary_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            victim = Path(directory) / "keep.txt"
            victim.write_text("unchanged")
            Path(directory, "source-management.tmp").symlink_to(victim)
            await SourceSettings(directory).set_enabled(True)
            self.assertEqual(victim.read_text(), "unchanged")

    async def test_inventory_keeps_system_apps_distinct_and_rejects_invalid_entries(self):
        result = packages("package:org.vendor.system\npackage:org.example.player\npackage:org.example.player\npackage:bad;command\n",
                          "package:org.vendor.system\n")
        self.assertEqual([item["package"] for item in result], ["org.example.player", "org.vendor.system"])
        self.assertTrue(result[-1]["system"])


class ProductIdentityTests(unittest.IsolatedAsyncioTestCase):
    async def check(self, body, status=200):
        async def chunks(_size):
            yield body
        response = Mock(status=status)
        response.content.iter_chunked = chunks
        context = Mock(__aenter__=AsyncMock(return_value=response), __aexit__=AsyncMock())
        client = Mock(get=Mock(return_value=context))
        session = Mock(__aenter__=AsyncMock(return_value=client), __aexit__=AsyncMock())
        with patch("gateway.sources.ClientSession", return_value=session) as factory:
            result = await matches_tv("192.0.2.10", TV_JID)
        factory.assert_called_once()
        self.assertFalse(factory.call_args.kwargs["trust_env"])
        client.get.assert_called_once_with("http://192.0.2.10:8080/BeoDevice", allow_redirects=False)
        return result

    async def test_only_exact_native_identity_is_accepted(self):
        data = {"beoDevice": {"productId": {"typeNumber": "7980", "itemNumber": "1234567", "serialNumber": "12345678"}}}
        self.assertTrue(await self.check(json.dumps(data).encode()))
        data["beoDevice"]["productId"]["serialNumber"] = "87654321"
        self.assertFalse(await self.check(json.dumps(data).encode()))

    async def test_redirect_invalid_and_oversized_replies_are_rejected(self):
        self.assertFalse(await self.check(b"{}", status=302))
        self.assertFalse(await self.check(b"invalid"))
        self.assertFalse(await self.check(b"x" * 65537))


class ControllerSourcesTests(SetupFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.adb = AsyncMock()
        self.adb.inspect.return_value = {"state": "connected", "model": "QM153E", "apps": []}
        self.controller.sources.adb = self.adb
        self.controller.sources.verify = AsyncMock(return_value=True)

    async def test_connect_reads_a_fresh_repaired_catalog_without_testing_a_source(self):
        await self.controller.scan()
        await self.controller.select(TV_JID)
        await self.controller.set_sources_enabled(True)
        self.adb.inspect.return_value = {"state": "connected", "helper_installed": True}
        editor = Mock()
        editor.refresh = AsyncMock(return_value={"state": "ready", "catalog": [], "entries": []})
        self.controller._source_editor = editor
        result = await self.controller.inspect_sources()
        editor.refresh.assert_awaited_once_with(self.adb, "192.0.2.10", TV_JID)
        self.assertEqual(result["helper"]["state"], "ready")
        self.adb.start_helper.assert_not_called()

    async def test_failed_registration_remains_visible_with_saved_shortcuts(self):
        await self.controller.scan()
        await self.controller.select(TV_JID)
        await self.controller.set_sources_enabled(True)
        self.adb.inspect.return_value = {"state": "connected", "helper_installed": True}
        editor = Mock()
        editor.refresh = AsyncMock(side_effect=ValueError("Occupied source alias"))
        editor.status = AsyncMock(return_value={"state": "attention", "error": "Occupied source alias", "entries": [{"id": "saved"}], "catalog": []})
        self.controller._source_editor = editor
        result = await self.controller.inspect_sources()
        self.assertEqual(result["helper"]["entries"], [{"id": "saved"}])
        self.assertEqual(result["helper"]["state"], "attention")

    async def test_fresh_connect_does_not_hide_gateway_owner_rejection(self):
        await self.controller.scan()
        await self.controller.select(TV_JID)
        await self.controller.set_sources_enabled(True)
        self.adb.inspect.return_value = {"state": "connected", "helper_installed": True}
        editor = Mock()
        editor.refresh = AsyncMock(side_effect=ValueError("Different gateway owner"))
        editor.status = AsyncMock(side_effect=ValueError("Different gateway owner"))
        self.controller._source_editor = editor
        with self.assertRaisesRegex(ValueError, "Different gateway owner"):
            await self.controller.inspect_sources()

    async def test_shared_selection_is_required_and_enable_does_not_touch_light_receiver(self):
        await self.controller.set_sources_enabled(True)
        with self.assertRaises(ValueError):
            await self.controller.inspect_sources()
        await self.controller.scan()
        await self.controller.select(TV_JID)
        events = list(self.events)
        result = await self.controller.inspect_sources()
        self.assertEqual(result["tv_jid"], TV_JID)
        self.adb.inspect.assert_awaited_once_with("192.0.2.10")
        self.assertEqual(self.events, events)

    async def test_inventory_still_works_when_only_light_reception_is_paused(self):
        await self.controller.scan()
        await self.controller.select(TV_JID)
        await self.controller.pause()
        await self.controller.set_sources_enabled(True)
        result = await self.controller.inspect_sources()
        self.assertEqual(result["state"], "connected")
        self.assertIsNone(self.controller.runtime)
        self.assertEqual(self.controller.state, "paused")

    async def test_resume_reuses_the_selection_and_never_picks_another_product(self):
        await self.controller.scan()
        await self.controller.select(TV_JID)
        await self.controller.pause()
        await self.controller.resume()
        self.assertEqual(self.controller.runtime.options.horizon_jid, TV_JID)
        self.assertTrue(self.controller.selection["enabled"])
        await self.controller.pause()
        self.controller.devices = [device(jid=TV_JID.replace("12345678", "87654321"))]
        await self.controller.resume()
        self.assertIsNone(self.controller.runtime)
        self.assertEqual(self.controller.selection["jid"], TV_JID)
        self.assertTrue(self.controller.selection["enabled"])

    async def test_rediscovery_uses_selected_identity_at_its_new_ip(self):
        await self.controller.scan()
        await self.controller.select(TV_JID)
        await self.controller.set_sources_enabled(True)
        self.controller.scanned_at = float("-inf")
        self.scanner.return_value = [device(address="192.0.2.40")]
        self.controller.sources.verify.side_effect = [False, True]
        await self.controller.inspect_sources()
        self.adb.inspect.assert_awaited_once_with("192.0.2.40")

    async def test_missing_selected_tv_never_falls_back_to_another_product(self):
        await self.controller.scan()
        await self.controller.select(TV_JID)
        await self.controller.set_sources_enabled(True)
        self.controller.scanned_at = float("-inf")
        self.scanner.return_value = [device(jid=TV_JID.replace("12345678", "87654321"))]
        self.controller.sources.verify.return_value = False
        with self.assertRaises(ValueError):
            await self.controller.inspect_sources()
        self.adb.inspect.assert_not_called()

    async def test_verified_receiver_address_works_when_mdns_record_is_missing(self):
        await self.controller.scan()
        await self.controller.select(TV_JID)
        await self.controller.set_sources_enabled(True)
        self.controller.devices = []
        self.scanner.return_value = []
        result = await self.controller.inspect_sources()
        self.assertEqual(result["tv_jid"], TV_JID)
        self.controller.sources.verify.assert_awaited_once_with("192.0.2.10", TV_JID)
        self.adb.inspect.assert_awaited_once_with("192.0.2.10")

    async def test_inventory_is_refused_until_extension_is_enabled(self):
        await self.controller.scan()
        await self.controller.select(TV_JID)
        with self.assertRaises(ValueError):
            await self.controller.inspect_sources()
        self.adb.inspect.assert_not_called()


class WebSourcesTests(SetupFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.adb = AsyncMock()
        self.controller.sources.adb = self.adb
        self.controller.sources.verify = AsyncMock(return_value=True)
        self.admin = AsyncMock(return_value=True)
        self.client = TestClient(TestServer(make_app(self.controller, allowed_peers={"127.0.0.1"}, admin_check=self.admin)))
        self.client.session.headers["X-Remote-User-Id"] = "0123456789abcdef" * 2
        await self.client.start_server()
        page = await (await self.client.get("/")).text()
        self.token = json.loads(re.search(r'const token = ("[^"]+");', page)[1])
        self.headers = {"X-Setup-Token": self.token}

    async def asyncTearDown(self):
        await self.client.close()
        await super().asyncTearDown()

    async def test_inventory_api_requires_current_admin_permission_and_page_token(self):
        for endpoint in ("options", "inventory"):
            response = await self.client.post("/api/sources/" + endpoint, json={})
            self.assertEqual(response.status, 403)
        self.admin.return_value = False
        response = await self.client.post("/api/sources/options", json={"enabled": True}, headers=self.headers)
        self.assertEqual(response.status, 403)
        self.admin.assert_awaited_with("0123456789abcdef" * 2, fresh=True)
        self.assertFalse(self.controller.sources.enabled)
        self.adb.inspect.assert_not_called()

    async def test_source_api_has_no_free_adb_commands_or_tv_address(self):
        response = await self.client.post("/api/sources/options", json={"enabled": "yes"}, headers=self.headers)
        self.assertEqual(response.status, 400)
        response = await self.client.post("/api/sources/inventory", json={"address": "192.0.2.99"}, headers=self.headers)
        self.assertEqual(response.status, 400)
        response = await self.client.post("/api/sources/inventory", json={"command": "reboot"}, headers=self.headers)
        self.assertEqual(response.status, 400)
        self.adb.inspect.assert_not_called()

    async def test_resume_api_is_protected_and_resumes_only_the_saved_tv(self):
        await self.controller.scan()
        await self.controller.select(TV_JID)
        await self.controller.pause()
        response = await self.client.post("/api/resume", json={})
        self.assertEqual(response.status, 403)
        self.admin.return_value = False
        response = await self.client.post("/api/resume", json={}, headers=self.headers)
        self.assertEqual(response.status, 403)
        self.assertIsNone(self.controller.runtime)
        self.admin.return_value = True
        response = await self.client.post("/api/resume", json={"jid": "other"}, headers=self.headers)
        self.assertEqual(response.status, 400)
        response = await self.client.post("/api/resume", json={}, headers=self.headers)
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["tv_jid"], TV_JID)
        self.assertIsNotNone(self.controller.runtime)

    async def test_authorization_and_failure_states_are_bounded(self):
        await self.controller.scan()
        await self.controller.select(TV_JID)
        response = await self.client.post("/api/sources/options", json={"enabled": True}, headers=self.headers)
        self.assertEqual(response.status, 200)
        self.adb.inspect.return_value = {"state": "authorization_required", "apps": []}
        response = await self.client.post("/api/sources/inventory", json={}, headers=self.headers)
        self.assertEqual((await response.json())["state"], "authorization_required")
        self.adb.inspect.side_effect = SourceError("adb_timeout")
        response = await self.client.post("/api/sources/inventory", json={}, headers=self.headers)
        self.assertEqual(response.status, 503)
        self.assertEqual((await response.json())["code"], "adb_timeout")


