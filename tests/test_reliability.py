import asyncio
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from unittest.mock import AsyncMock, Mock, patch

from aiohttp import web
from aiohttp.test_utils import TestServer

from gateway.buttons import ButtonFilter
from gateway.discovery import Announcer
from gateway.events import EventPublisher
from gateway.health import HealthReporter, check_health
from gateway.protocol import stream_header
from gateway.server import GatewayServer
from test_gateway import TV, GATEWAY, options, forward


def event(command=15, address=27, originator="0"):
    raw = bytes([0, address, 0, 0, command, 0, 0, 0, 0, 0, 0, 0, 0])
    return {"peer_jid": TV, "originator": originator, "data_hex": raw.hex()}


class ButtonTests(unittest.TestCase):
    def test_repeat_is_ignored_but_new_press_after_release_is_kept(self):
        clock = [0.0]
        buttons = ButtonFilter(clock=lambda: clock[0])
        self.assertTrue(buttons.accept(event()))
        clock[0] = 0.2
        self.assertFalse(buttons.accept(event()))
        self.assertTrue(buttons.accept(event(126)))
        clock[0] = 0.4
        self.assertTrue(buttons.accept(event()))

    def test_fast_different_scene_is_kept_and_missing_release_recovers(self):
        clock = [0.0]
        buttons = ButtonFilter(clock=lambda: clock[0])
        self.assertTrue(buttons.accept(event()))
        clock[0] = 0.01
        self.assertTrue(buttons.accept(event(37)))
        clock[0] = 3.0
        self.assertTrue(buttons.accept(event(37)))

    def test_transport_bounce_after_release_is_suppressed(self):
        clock = [0.0]
        buttons = ButtonFilter(clock=lambda: clock[0])
        self.assertTrue(buttons.accept(event()))
        self.assertTrue(buttons.accept(event(126)))
        clock[0] = 0.03
        self.assertFalse(buttons.accept(event()))

    def test_control_and_non_light_frames_remain_raw(self):
        buttons = ButtonFilter()
        for sample in (event(15, address=28), {**event(), "data_hex": "001b01000f0000000000000000"}):
            self.assertTrue(buttons.accept(sample))
            self.assertTrue(buttons.accept(sample))

    def test_unbounded_originators_do_not_grow_tracking_forever(self):
        buttons = ButtonFilter()
        for index in range(1000):
            buttons.accept(event(originator=str(index)))
        self.assertLessEqual(len(buttons.pressed), 32)
        self.assertLessEqual(len(buttons.recent), 32)


class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_backlog_after_outage_expires_but_new_press_is_delivered(self):
        clock = [0.0]
        started, release = threading.Event(), threading.Event()
        delivered = []
        publisher = EventPublisher("synthetic-test-token", clock=lambda: clock[0], wall_clock=lambda: 1000.0)

        def post(sample):
            delivered.append(sample)
            if len(delivered) == 1:
                started.set()
                release.wait(1)

        publisher._post = post
        await publisher.start()
        try:
            publisher.submit(event())
            self.assertTrue(await asyncio.to_thread(started.wait, 1))
            publisher.submit(event(37))
            clock[0] = 3.0
            publisher.submit(event(38))
            release.set()
            await asyncio.wait_for(publisher.queue.join(), 1)
            self.assertEqual(delivered, [{**event(), "received_at": 1000.0}, {**event(38), "received_at": 1000.0}])
            self.assertEqual(publisher.expired, 1)
        finally:
            release.set()
            await publisher.close()

    async def test_expired_commands_are_never_posted(self):
        clock = [0.0]
        publisher = EventPublisher("synthetic-test-token", clock=lambda: clock[0], wall_clock=lambda: 1000.0)
        publisher._post = Mock()
        publisher.submit(event())
        clock[0] = 2.1
        await publisher.start()
        try:
            await asyncio.wait_for(publisher.queue.join(), 1)
            publisher._post.assert_not_called()
            self.assertEqual(publisher.expired, 1)
            publisher.submit(event(37))
            await asyncio.wait_for(publisher.queue.join(), 1)
            publisher._post.assert_called_once_with({**event(37), "received_at": 1000.0})
        finally:
            await publisher.close()

    async def test_failed_post_is_not_retried_and_next_press_recovers(self):
        publisher = EventPublisher("synthetic-test-token")
        publisher._post = Mock(side_effect=[TimeoutError("response lost"), None])
        await publisher.start()
        try:
            publisher.submit(event())
            await asyncio.wait_for(publisher.queue.join(), 1)
            self.assertEqual(publisher._post.call_count, 1)
            self.assertEqual(publisher.last_result, "unavailable")
            publisher.submit(event(37))
            await asyncio.wait_for(publisher.queue.join(), 1)
            self.assertEqual(publisher._post.call_count, 2)
            self.assertEqual(publisher.last_result, "ok")
            self.assertEqual(publisher.published, 1)
        finally:
            await publisher.close()

    async def test_overloaded_queue_drops_without_blocking_receiver(self):
        publisher = EventPublisher("synthetic-test-token", queue_size=1, wall_clock=lambda: 1000.0)
        publisher._post = Mock()
        publisher.submit(event())
        publisher.submit(event(37))
        self.assertEqual(publisher.dropped, 1)
        await publisher.start()
        try:
            await asyncio.wait_for(publisher.queue.join(), 1)
            publisher._post.assert_called_once_with({**event(), "received_at": 1000.0})
        finally:
            await publisher.close()

    async def test_receipt_time_survives_queue_delay_and_caller_is_not_mutated(self):
        wall_clock = [1000.0]
        publisher = EventPublisher("synthetic-test-token", wall_clock=lambda: wall_clock[0])
        publisher._post = Mock()
        sample = event()
        publisher.submit(sample)
        self.assertNotIn("received_at", sample)
        wall_clock[0] = 1001.0
        await publisher.start()
        try:
            await asyncio.wait_for(publisher.queue.join(), 1)
            publisher._post.assert_called_once_with({**sample, "received_at": 1000.0})
        finally:
            await publisher.close()

    async def test_event_credentials_bypass_environment_proxy_and_redirects(self):
        origin_seen, proxy_seen = [], []
        async def origin(request):
            origin_seen.append((request.path, request.headers.get("Authorization")))
            if request.path == "/redirect":
                raise web.HTTPFound("/unexpected")
            return web.Response(status=200)
        async def proxy(request):
            proxy_seen.append(request.headers.get("Authorization"))
            return web.Response(status=200)
        app, proxy_app = web.Application(), web.Application()
        app.router.add_route("*", "/{path:.*}", origin)
        proxy_app.router.add_route("*", "/{path:.*}", proxy)
        async with TestServer(app) as server, TestServer(proxy_app) as proxy_server:
            with patch("urllib.request.getproxies", return_value={"http": str(proxy_server.make_url('/'))}), \
                    patch("urllib.request.proxy_bypass", return_value=False):
                publisher = EventPublisher("synthetic-test-token")
                with patch("gateway.events.EVENT_URL", str(server.make_url('/event'))):
                    await asyncio.to_thread(publisher._post, event())
                with patch("gateway.events.EVENT_URL", str(server.make_url('/redirect'))):
                    with self.assertRaises(HTTPError):
                        await asyncio.to_thread(publisher._post, event())
        self.assertEqual(proxy_seen, [])
        self.assertEqual([path for path, _ in origin_seen], ["/event", "/redirect"])
        self.assertTrue(all(auth == "Bearer synthetic-test-token" for _, auth in origin_seen))


class HealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_heartbeat_goes_unhealthy_when_stale_or_worker_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "health.json"
            healthy = [True]
            reporter = HealthReporter(lambda: {"healthy": healthy[0]}, path=path)
            await reporter.start()
            try:
                self.assertTrue(check_health(path))
                updated = json.loads(path.read_text())["updated_monotonic"]
                self.assertFalse(check_health(path, now=updated + 21))
                healthy[0] = False
                reporter.write()
                self.assertFalse(check_health(path))
            finally:
                await reporter.close()
            self.assertFalse(path.exists())

    async def test_health_write_does_not_follow_a_preexisting_temporary_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "health.json"
            victim = Path(directory) / "unrelated.txt"
            victim.write_text("keep me")
            path.with_suffix(".tmp").symlink_to(victim)
            reporter = HealthReporter(lambda: {"healthy": True}, path=path)
            reporter.write()
            self.assertEqual(victim.read_text(), "keep me")
            self.assertTrue(check_health(path))

    async def test_missing_or_invalid_health_is_not_healthy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "health.json"
            self.assertFalse(check_health(path))
            for content in ('not json', '[]', '{"healthy":true,"updated_monotonic":true}'):
                path.write_text(content)
                self.assertFalse(check_health(path))


class ConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_idle_peer_is_allowed_but_unfinished_frame_times_out(self):
        server = GatewayServer(options(), Mock(), frame_timeout=0.05)
        await server.start(host="127.0.0.1", port=0)
        reader, writer = await asyncio.open_connection("127.0.0.1", server.server.sockets[0].getsockname()[1])
        try:
            writer.write(stream_header(TV, GATEWAY))
            await writer.drain()
            self.assertTrue(await asyncio.wait_for(reader.read(4096), 1))
            await asyncio.sleep(0.1)
            self.assertEqual(len(server.clients), 1)
            writer.write(b"<message")
            await writer.drain()
            self.assertEqual(await asyncio.wait_for(reader.read(), 1), b"")
        finally:
            writer.close()
            await writer.wait_closed()
            await server.close()

    async def test_completed_frames_renew_deadline_for_the_next_partial_frame(self):
        capture = Mock()
        server = GatewayServer(options(), capture, frame_timeout=0.12)
        await server.start(host="127.0.0.1", port=0)
        reader, writer = await asyncio.open_connection("127.0.0.1", server.server.sockets[0].getsockname()[1])
        message = forward().encode()
        split = len(message) // 2
        try:
            writer.write(stream_header(TV, GATEWAY))
            await writer.drain()
            await asyncio.wait_for(reader.read(4096), 1)
            writer.write(message[:split])
            await writer.drain()
            for _ in range(4):
                await asyncio.sleep(0.06)
                writer.write(message[split:] + message[:split])
                await writer.drain()
            writer.write(message[split:])
            await writer.drain()
            await asyncio.sleep(0.01)
            self.assertEqual(capture.call_count, 5)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass
            await server.close()

    async def test_trickling_an_unfinished_frame_cannot_extend_its_deadline(self):
        capture = Mock()
        server = GatewayServer(options(), capture, frame_timeout=0.12)
        await server.start(host="127.0.0.1", port=0)
        reader, writer = await asyncio.open_connection("127.0.0.1", server.server.sockets[0].getsockname()[1])
        async def trickle():
            try:
                writer.write(b"<message")
                await writer.drain()
                for _ in range(20):
                    await asyncio.sleep(0.03)
                    writer.write(b" ")
                    await writer.drain()
            except ConnectionError:
                pass
        task = None
        try:
            writer.write(stream_header(TV, GATEWAY))
            await writer.drain()
            self.assertTrue(await asyncio.wait_for(reader.read(4096), 1))
            task = asyncio.create_task(trickle())
            self.assertEqual(await asyncio.wait_for(reader.read(), 0.3), b"")
            capture.assert_not_called()
        finally:
            if task is not None:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass
            await server.close()


class DiscoveryRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_announcement_is_recreated_after_network_failure(self):
        announcer = Announcer(options())
        stop = asyncio.Event()
        starts = []

        async def start():
            starts.append(True)
            announcer.zeroconf = Mock(async_update_service=AsyncMock(side_effect=OSError("network down")))
            announcer.advertised = True
            if len(starts) == 2:
                stop.set()

        async def close():
            announcer.zeroconf = None
            announcer.advertised = False

        announcer.start, announcer.close = start, close
        await asyncio.wait_for(announcer.serve(stop, interval=0.01, retry_delay=0.01), 1)
        self.assertEqual(len(starts), 2)
        self.assertEqual(announcer.retries, 1)

    async def test_network_start_failure_recovers_without_restarting_receiver(self):
        announcer = Announcer(options())
        stop = asyncio.Event()
        starts = []

        async def start():
            starts.append(time.monotonic())
            if len(starts) == 1:
                raise OSError("interface not ready")
            announcer.zeroconf = object()
            announcer.advertised = True
            stop.set()

        async def close():
            announcer.zeroconf = None
            announcer.advertised = False

        announcer.start = start
        announcer.close = close
        await asyncio.wait_for(announcer.serve(stop, retry_delay=0.01), 1)
        self.assertEqual(len(starts), 2)
        self.assertEqual(announcer.retries, 1)
