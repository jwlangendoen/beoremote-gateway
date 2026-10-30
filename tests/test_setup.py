import asyncio
import json
from pathlib import Path
import re
import socket
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

from aiohttp.test_utils import TestClient, TestServer
from zeroconf import ServiceInfo

from gateway.autodetect import device_record, discover_devices, route_address
from gateway.config import Options
from gateway.runtime import GatewayRuntime
from gateway.setup import SetupController, read_selection, save_selection
from gateway.web import ingress_port, make_app
from test_gateway import TV

OTHER = TV.replace("12345678", "87654321")


def device(jid=TV, address="192.0.2.10", name="Living room TV"):
    return {"jid": jid, "name": name, "addresses": [address]}


class FakeRuntime:
    def __init__(self, options, events):
        self.options, self.events = options, events

    async def start(self):
        self.events.append(("start", self.options.horizon_address))

    async def close(self):
        self.events.append(("close", self.options.horizon_address))

    def snapshot(self):
        return {"healthy": True, "listener": True, "discovery": True, "peers": 0,
                "received": 0, "suppressed": 0, "ha": {"delivery": "idle"}}


class AutodetectionTests(unittest.TestCase):
    def info(self, jid=TV, addresses=None, node="beocore"):
        return ServiceInfo("_beocore._tcp.local.", "Test._beocore._tcp.local.",
                           parsed_addresses=addresses or ["192.0.2.10"], port=5222,
                           properties={"jid": jid, "name": "Living room TV", "node": node})

    def test_only_valid_product_records_with_unicast_ipv4_are_offered(self):
        self.assertEqual(device_record(self.info()), device())
        for info in (self.info(jid=Options().gateway_jid), self.info(jid="not-an-identity"),
                     self.info(node="other"), self.info(addresses=["::1"]),
                     self.info(addresses=["127.0.0.1"])):
            self.assertIsNone(device_record(info))
        self.assertIsNone(device_record(self.info(), excluded_jid=TV))

    def test_address_detection_uses_route_without_sending_a_datagram(self):
        connection = Mock()
        connection.getsockname.return_value = ("192.0.2.20", 1234)
        context = Mock()
        context.__enter__ = Mock(return_value=connection)
        context.__exit__ = Mock(return_value=False)
        with patch("gateway.autodetect.socket.socket", return_value=context):
            self.assertEqual(route_address(["192.0.2.10"]), ("192.0.2.10", "192.0.2.20"))
        connection.connect.assert_called_once_with(("192.0.2.10", 9))
        connection.send.assert_not_called()
        connection.sendto.assert_not_called()

    def test_selection_file_rejects_invalid_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "selection.json"
            for value in ([], {"jid": TV, "name": "TV", "enabled": "yes"},
                          {"jid": "invalid", "name": "TV", "enabled": True}):
                path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    read_selection(path)
            selected = {"jid": TV, "name": "TV", "enabled": True}
            save_selection(path, selected)
            self.assertEqual(read_selection(path), selected)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class ScanTests(unittest.IsolatedAsyncioTestCase):
    async def test_ingress_uses_supervisor_allocated_port_without_redirecting_credentials(self):
        response = Mock(status=200, json=AsyncMock(return_value={"data": {"ingress_port": 62999}}))
        response_context = Mock(__aenter__=AsyncMock(return_value=response), __aexit__=AsyncMock())
        client = Mock(get=Mock(return_value=response_context))
        client_context = Mock(__aenter__=AsyncMock(return_value=client), __aexit__=AsyncMock())
        with patch.dict("os.environ", {"SUPERVISOR_TOKEN": "synthetic-test-token"}), \
                patch("gateway.web.ClientSession", return_value=client_context):
            self.assertEqual(await ingress_port(), 62999)
        self.assertFalse(client.get.call_args.kwargs["allow_redirects"])
        response.json.return_value = {"data": {"ingress_port": 0}}
        with patch.dict("os.environ", {"SUPERVISOR_TOKEN": "synthetic-test-token"}), \
                patch("gateway.web.ClientSession", return_value=client_context):
            with self.assertRaises(ValueError):
                await ingress_port()

    async def test_standalone_container_does_not_request_supervisor(self):
        with patch.dict("os.environ", {}, clear=True), patch("gateway.web.ClientSession") as session:
            self.assertEqual(await ingress_port(), 8099)
            session.assert_not_called()

    async def test_async_scan_resolves_records_and_closes_resources(self):
        from zeroconf import ServiceStateChange
        zc = Mock()
        zc.async_close = AsyncMock()
        info = Mock(properties={b"jid": TV.encode(), b"name": b"TV", b"node": b"beocore"})
        info.parsed_addresses.return_value = ["192.0.2.10"]
        info.async_request = AsyncMock(return_value=True)
        browser = Mock(async_cancel=AsyncMock())

        def start_browser(_zc, service, handlers):
            handlers[0](zeroconf=_zc, service_type=service,
                        name="Test." + service, state_change=ServiceStateChange.Added)
            return browser

        with patch("zeroconf.asyncio.AsyncZeroconf", return_value=zc), \
                patch("zeroconf.asyncio.AsyncServiceBrowser", side_effect=start_browser), \
                patch("zeroconf.asyncio.AsyncServiceInfo", return_value=info):
            self.assertEqual(await discover_devices(duration=0), [device(name="TV")])
        browser.async_cancel.assert_awaited_once()
        zc.async_close.assert_awaited_once()


class RuntimeLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def options(self, publish=False):
        return Options.from_dict({"mode": "advertise", "horizon_address": "192.0.2.10",
                                  "horizon_jid": TV, "advertise_address": "192.0.2.20",
                                  "publish_ha_events": publish})

    async def test_receiver_and_discovery_are_closed_together(self):
        server = Mock(start=AsyncMock(), close=AsyncMock(), clients={}, received=0)
        server.server.is_serving.return_value = True
        async def wait(stop):
            await stop.wait()
        announcer = Mock(serve=AsyncMock(side_effect=wait), advertised=True)
        with patch("gateway.runtime.GatewayServer", return_value=server), \
                patch("gateway.runtime.Announcer", return_value=announcer):
            runtime = GatewayRuntime(self.options())
            await runtime.start()
            await asyncio.sleep(0)
            self.assertTrue(runtime.snapshot()["healthy"])
            await runtime.close()
        server.close.assert_awaited_once()
        self.assertTrue(runtime.discovery_task.done())

    async def test_failed_bind_closes_started_publisher(self):
        server = Mock(start=AsyncMock(side_effect=OSError("Port in use")), close=AsyncMock())
        publisher = Mock(start=AsyncMock(), close=AsyncMock())
        with patch("gateway.runtime.GatewayServer", return_value=server), \
                patch("gateway.runtime.EventPublisher", return_value=publisher), \
                patch.dict("os.environ", {"SUPERVISOR_TOKEN": "synthetic-test-token"}):
            runtime = GatewayRuntime(self.options(publish=True))
            with self.assertRaises(OSError):
                await runtime.start()
        server.close.assert_awaited_once()
        publisher.close.assert_awaited_once()


class SetupFixture:
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "selection.json"
        self.scanner = AsyncMock(return_value=[device(), device(OTHER, "192.0.2.11", "Other product")])
        self.events = []
        self.route = Mock(side_effect=lambda addresses: (addresses[0], "192.0.2.20"))
        self.controller = self.make_controller()

    def make_controller(self, options=None):
        return SetupController(options or Options(mode="auto"), path=self.path,
                               scanner=self.scanner, route=self.route,
                               runtime_factory=lambda options: FakeRuntime(options, self.events))

    async def asyncTearDown(self):
        await self.controller.close()
        self.directory.cleanup()


class ControllerTests(SetupFixture, unittest.IsolatedAsyncioTestCase):
    async def test_fresh_setup_does_not_choose_or_start_a_device(self):
        self.controller = self.make_controller(Options.from_dict({}))
        await self.controller.start()
        await asyncio.sleep(0)
        self.scanner.assert_not_called()
        await self.controller.scan()
        self.assertIsNone(self.controller.selection)
        self.assertIsNone(self.controller.runtime)
        self.assertTrue(self.controller.snapshot()["healthy"])

    async def test_selected_identity_is_persisted_without_ip_and_only_one_runtime_runs(self):
        await self.controller.scan()
        await self.controller.select(TV)
        self.assertEqual(read_selection(self.path), {"jid": TV, "name": "Living room TV", "enabled": True})
        self.assertNotIn("192.0.2", self.path.read_text())
        self.assertEqual(self.controller.runtime.options.advertise_address, "192.0.2.20")
        self.assertTrue(self.controller.runtime.options.publish_ha_events)
        await self.controller.select(OTHER)
        self.assertEqual(self.events, [("start", "192.0.2.10"), ("close", "192.0.2.10"), ("start", "192.0.2.11")])

    async def test_unseen_or_stale_selection_is_rejected(self):
        with self.assertRaises(ValueError):
            await self.controller.select(TV)
        await self.controller.scan()
        self.controller.scanned_at = time.monotonic() - 61
        self.scanner.return_value = []
        with self.assertRaises(ValueError):
            await self.controller.select(TV)
        self.assertFalse(self.path.exists())

    async def test_older_device_list_is_refreshed_when_choosing_a_tv(self):
        await self.controller.scan()
        self.controller.scanned_at = time.monotonic() - 61
        self.scanner.return_value = [device(address="192.0.2.12")]
        await self.controller.select(TV)
        self.assertEqual(self.controller.runtime.options.horizon_address, "192.0.2.12")
        self.assertEqual(self.scanner.await_count, 2)

    async def test_dhcp_change_reconfigures_same_identity_and_never_falls_back(self):
        await self.controller.scan()
        await self.controller.select(TV)
        self.scanner.return_value = [device(address="192.0.2.12")]
        self.controller.scanned_at = float("-inf")
        await self.controller.reconcile()
        self.assertEqual(self.controller.runtime.options.horizon_address, "192.0.2.12")
        self.assertEqual(self.events[-2:], [("close", "192.0.2.10"), ("start", "192.0.2.12")])
        self.scanner.return_value = [device(OTHER, "192.0.2.11")]
        self.controller.scanned_at = float("-inf")
        await self.controller.reconcile()
        self.assertEqual(self.controller.runtime.options.horizon_jid, TV)
        self.assertEqual(self.controller.runtime.options.horizon_address, "192.0.2.12")

    async def test_saved_device_is_rediscovered_after_restart(self):
        save_selection(self.path, {"jid": TV, "name": "TV", "enabled": True})
        await self.controller.start()
        await self.controller.reconcile()
        self.assertEqual(self.controller.runtime.options.horizon_jid, TV)
        self.assertEqual(self.events, [("start", "192.0.2.10")])

    async def test_paused_setup_stays_paused_after_restart(self):
        await self.controller.scan()
        await self.controller.select(TV)
        await self.controller.pause()
        self.assertIsNone(self.controller.runtime)
        restarted = self.make_controller()
        try:
            await restarted.start()
            await asyncio.sleep(0)
            self.assertEqual(restarted.state, "paused")
            self.assertIsNone(restarted.runtime)
        finally:
            await restarted.close()

    async def test_manual_settings_still_work_without_scanning(self):
        self.controller = self.make_controller(Options.from_dict({
            "mode": "advertise", "horizon_address": "192.0.2.10", "horizon_jid": TV,
            "advertise_address": "192.0.2.20"}))
        await self.controller.start()
        self.scanner.assert_not_called()
        self.assertEqual(self.controller.state, "active")
        with self.assertRaises(ValueError):
            await self.controller.select(TV)

    async def test_network_or_bind_failure_is_visible_and_can_recover(self):
        await self.controller.scan()
        self.route.side_effect = OSError("No route")
        await self.controller.select(TV)
        self.assertEqual(self.controller.state, "error")
        self.assertIn("No route", self.controller.status()["error"])
        self.assertIsNone(self.controller.runtime)
        self.route.side_effect = lambda addresses: (addresses[0], "192.0.2.20")
        await self.controller.reconcile()
        self.assertEqual(self.controller.state, "active")


class SetupWebTests(SetupFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.client = TestClient(TestServer(make_app(self.controller, allowed_peers={"127.0.0.1"})))
        await self.client.start_server()
        response = await self.client.get("/", headers={"X-Ingress-Path": "/api/hassio_ingress/test-session"})
        self.page = await response.text()
        self.token = json.loads(re.search(r'const token = ("[^"]+");', self.page)[1])
        self.headers = {"X-Setup-Token": self.token}

    async def asyncTearDown(self):
        await self.client.close()
        await super().asyncTearDown()

    async def test_setup_flow_discovers_selects_and_pauses_from_ingress(self):
        response = await self.client.get("/api/devices")
        self.assertEqual(response.status, 200)
        self.assertEqual(len((await response.json())["devices"]), 2)
        response = await self.client.post("/api/select", json={"jid": TV}, headers=self.headers)
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["state"], "active")
        response = await self.client.post("/api/pause", json={}, headers=self.headers)
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["state"], "paused")

    async def test_write_requires_page_token_and_discovered_identity(self):
        for headers in ({}, {"X-Setup-Token": "not-the-page-token"}):
            response = await self.client.post("/api/select", json={"jid": TV}, headers=headers)
            self.assertEqual(response.status, 403)
        response = await self.client.post("/api/select", json={"jid": "unknown"}, headers=self.headers)
        self.assertEqual(response.status, 400)
        self.assertFalse(self.path.exists())

    async def test_ingress_prefix_and_html_are_safe_for_device_names(self):
        self.assertIn('const base = new URL("/api/hassio_ingress/test-session/"', self.page)
        self.assertIn("textContent=device.name", self.page)
        self.assertNotIn("innerHTML", self.page)
        response = await self.client.get("/")
        self.assertIn("script-src 'nonce-", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    async def test_direct_lan_access_is_denied_even_with_spoofed_forwarding_header(self):
        client = TestClient(TestServer(make_app(self.controller)))
        await client.start_server()
        try:
            response = await client.get("/api/status", headers={"X-Forwarded-For": "172.30.32.2", "X-Real-IP": "172.30.32.2"})
            self.assertEqual(response.status, 403)
        finally:
            await client.close()
