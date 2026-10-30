import asyncio
import base64
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

from gateway.config import Options
from gateway.events import EVENT_URL, EventPublisher
from gateway.protocol import (
    CAPABILITIES, CLIENT, DISCO, PRODUCT, TUNNEL, capability_hash,
    decode_forward, read_response, stream_header,
)
from gateway.server import GatewayServer
from gateway.xmlstream import StreamParser
from gateway.__main__ import run

TV = "7980.1234567.12345678@products.bang-olufsen.com"
GATEWAY = Options().gateway_jid
RAW = bytes(range(13))  # Synthetic payload for malformed-input and stream tests.


def request(payload, identifier="9001", kind="set"):
    return (f'<iq xmlns="{CLIENT}" type="{kind}" id="{identifier}" '
            f'from="{TV}" to="{GATEWAY}">{payload}</iq>')


def forward(raw=RAW, timestamp="123456"):
    return (f'<message xmlns="{CLIENT}" from="{TV}" to="{GATEWAY}"><body>'
            f'<Forward xmlns="{TUNNEL}"><originator>{TV}</originator><telegram>'
            f'<data>{base64.b64encode(raw).decode()}</data><timestamp>{timestamp}</timestamp>'
            '</telegram></Forward></body></message>')


def options(**extra):
    return Options.from_dict({"mode": "listen", "horizon_address": "127.0.0.1",
                              "horizon_jid": TV, **extra})


class ProtocolTests(unittest.TestCase):
    def test_real_horizon_payload_values_in_reconstructed_envelopes(self):
        capture = json.loads((Path(__file__).parent / "fixtures/verified_light_telegrams.json").read_text())
        for sample in capture["samples"]:
            with self.subTest(label=sample["label"], phase=sample["phase"]):
                # Envelope is reconstructed; payload values are real captures.
                raw = base64.b64decode(sample["data_base64"], validate=True)
                wire = forward(raw, str(capture["timestamp"])).replace(
                    f"<originator>{TV}</originator>", f'<originator>{capture["originator"]}</originator>')
                event = decode_forward(ET.fromstring(wire))
                self.assertEqual(event["data_hex"], sample["data_hex"])
                self.assertEqual(event["originator"], "0")
                self.assertEqual(event["timestamp"], 1)
                self.assertEqual(raw[1], 27)
                self.assertEqual(raw[4], sample["command_byte"])

    def test_hash_matches_recorded_horizon_discovery(self):
        actual_tv_capabilities = ["beocore.configuration.1", "beocore.notifications.1",
                                 "beocore.player.1", *CAPABILITIES]
        self.assertEqual(capability_hash(actual_tv_capabilities), "eyfPLU/ws6IfsIEYc4mWUQPQy/o=")
        self.assertEqual(capability_hash(), "zFUJeqgUV9rBfrZ9zcyMcfTYsUc=")

    def test_contact_envelope_and_decimal_id(self):
        stanza = ET.fromstring(request(f'<GetContactInfo xmlns="{PRODUCT}"/>'))
        response = ET.fromstring(read_response(stanza, GATEWAY, TV, "Licht & scènes"))
        self.assertEqual(response.get("type"), "result")
        self.assertEqual(response.get("id"), "9001")
        self.assertEqual(response.findtext(f"{{{PRODUCT}}}GetContactInfo/{{{PRODUCT}}}contactInfo/{{{PRODUCT}}}name"), "Licht & scènes")
        stanza.set("id", "named-request")
        response = ET.fromstring(read_response(stanza, GATEWAY, TV, "Licht"))
        self.assertEqual(response.get("type"), "error")

    def test_unsupported_commands_get_error(self):
        for command in ("SetVolume", "Attach", "AllStandby"):
            stanza = ET.fromstring(request(f'<{command} xmlns="{PRODUCT}"/>'))
            response = ET.fromstring(read_response(stanza, GATEWAY, TV, "Licht"))
            self.assertEqual(response.get("type"), "error")

    def test_forward_is_raw_and_rejects_malformed_payloads(self):
        result = decode_forward(ET.fromstring(forward()))
        self.assertEqual(result["data_hex"], RAW.hex())
        self.assertEqual(result["timestamp"], 123456)
        self.assertNotIn("command", result)
        for stanza in (forward(raw=b"short"), forward(timestamp="-1"),
                       forward(timestamp="4294967296"), forward(timestamp="not-a-number"),
                       forward().replace(base64.b64encode(RAW).decode(), "%%%")):
            with self.assertRaises(ValueError):
                decode_forward(ET.fromstring(stanza))


class ParserTests(unittest.TestCase):
    def test_bytewise_stream_with_multiple_stanzas(self):
        parser = StreamParser()
        wire = stream_header(TV, GATEWAY) + request(f'<GetContactInfo xmlns="{PRODUCT}"/>').encode()
        wire += forward().encode() + b"</stream:stream>"
        events = []
        for byte in wire:
            events.extend(parser.feed(bytes([byte])))
        self.assertEqual([kind for kind, _ in events], ["open", "stanza", "stanza", "close"])
        self.assertEqual(decode_forward(events[2][1])["data_hex"], RAW.hex())

    def test_dtd_and_entity_declarations_are_rejected(self):
        data = b'<!DOCTYPE stream [<!ENTITY bad "payload">]>' + stream_header(TV, GATEWAY)
        parser = StreamParser()
        with self.assertRaises(ValueError):
            for byte in data:
                parser.feed(bytes([byte]))

    def test_unbounded_or_deep_input_is_rejected(self):
        parser = StreamParser()
        parser.feed(stream_header(TV, GATEWAY))
        with self.assertRaises(ValueError):
            for _ in range(17):
                parser.feed(b" " * 4096)
        parser = StreamParser()
        parser.feed(stream_header(TV, GATEWAY))
        with self.assertRaises(ValueError):
            parser.feed(b"<a>" * 25)


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_mode_opens_no_server_or_discovery(self):
        stop = asyncio.Event()
        stop.set()
        with patch("gateway.runtime.GatewayServer") as server, patch("gateway.runtime.Announcer") as announcer:
            await run(Options.from_dict({"mode": "disabled"}), stop)
        server.assert_not_called()
        announcer.assert_not_called()

    async def test_real_loopback_handshake_and_synthetic_forward(self):
        received = []
        ready = asyncio.Event()

        def capture(event):
            received.append(event)
            ready.set()

        server = GatewayServer(options(), capture)
        await server.start(host="127.0.0.1", port=0)
        port = server.server.sockets[0].getsockname()[1]
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        try:
            writer.write(stream_header(TV, GATEWAY))
            writer.write(request(f'<query xmlns="{DISCO}"/>', "xmpp7", "get").encode())
            writer.write(request(f'<GetContactInfo xmlns="{PRODUCT}"/>').encode())
            writer.write(request(f'<SetVolume xmlns="{PRODUCT}"/>', "9002").encode())
            await writer.drain()
            parser, stanzas = StreamParser(), []
            while len(stanzas) < 4:
                data = await asyncio.wait_for(reader.read(4096), timeout=2)
                self.assertTrue(data)
                stanzas.extend(value for kind, value in parser.feed(data) if kind == "stanza")
            replies = {stanza.get("id"): stanza for stanza in stanzas}
            self.assertEqual(replies["1"].get("type"), "get")
            self.assertEqual(replies["xmpp7"].get("type"), "result")
            self.assertEqual(replies["9001"].get("type"), "result")
            self.assertEqual(replies["9002"].get("type"), "error")
            # Fragment the actual TCP payload, as a peer is free to do.
            message = forward().encode()
            for chunk in (message[:17], message[17:123], message[123:]):
                writer.write(chunk)
                await writer.drain()
            await asyncio.wait_for(ready.wait(), timeout=2)
            self.assertEqual(received[0]["data_hex"], RAW.hex())
        finally:
            writer.close()
            await writer.wait_closed()
            await server.close()

    async def test_wrong_stream_identity_is_disconnected(self):
        capture = Mock()
        server = GatewayServer(options(), capture)
        await server.start(host="127.0.0.1", port=0)
        reader, writer = await asyncio.open_connection("127.0.0.1", server.server.sockets[0].getsockname()[1])
        try:
            writer.write(stream_header("other@products.bang-olufsen.com", GATEWAY))
            await writer.drain()
            self.assertEqual(await asyncio.wait_for(reader.read(), timeout=2), b"")
            capture.assert_not_called()
        finally:
            writer.close()
            await writer.wait_closed()
            await server.close()

    async def test_ha_publisher_uses_only_event_endpoint(self):
        publisher = EventPublisher("synthetic-test-token", wall_clock=lambda: 1234.0)
        response = Mock()
        response.status = 200
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        publisher.opener.open = Mock(return_value=context)
        await publisher.start()
        try:
            publisher.submit({"data_hex": RAW.hex()})
            await asyncio.wait_for(publisher.queue.join(), timeout=2)
            req = publisher.opener.open.call_args.args[0]
            self.assertEqual(req.full_url, EVENT_URL)
            self.assertEqual(req.get_method(), "POST")
            self.assertEqual(json.loads(req.data), {"data_hex": RAW.hex(), "received_at": 1234.0})
        finally:
            await publisher.close()


class ConfigurationTests(unittest.TestCase):
    def test_active_mode_requires_explicit_tv_and_advertise_address(self):
        self.assertEqual(Options.from_dict({}).mode, "auto")
        for invalid in ({"mode": "listen"}, {"mode": "advertise"},
                        {"publish_ha_events": "false"}, {"xmpp_port": True},
                        {"gateway_jid": "bad identity"}, {"gateway_name": "  "},
                        {"gateway_name": "Bad\x01name"}, {"log_level": "verbose"}):
            with self.assertRaises(ValueError):
                Options.from_dict(invalid)
        with self.assertRaises(ValueError):
            options(mode="advertise")


if __name__ == "__main__":
    unittest.main()
