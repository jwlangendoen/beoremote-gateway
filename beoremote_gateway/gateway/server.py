"""Inbound XMPP receiver; never sends media or light-control commands."""
import asyncio
import logging
import socket
import xml.etree.ElementTree as ET

from .protocol import CLIENT, DISCO, decode_forward, iq, read_response, stream_header
from .xmlstream import StreamParser

LOG = logging.getLogger(__name__)


class GatewayServer:
    def __init__(self, options, on_telegram, frame_timeout=5):
        self.options = options
        self.on_telegram = on_telegram
        self.server = None
        self.clients = {}
        self.received = 0
        self.frame_timeout = frame_timeout

    async def start(self, host="0.0.0.0", port=None):
        self.server = await asyncio.start_server(
            self._accept, host, self.options.xmpp_port if port is None else port)
        LOG.info("xmpp_listening port=%s", self.server.sockets[0].getsockname()[1])

    async def close(self):
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
        tasks = list(self.clients.values())
        for writer in list(self.clients):
            writer.close()
        if tasks:
            try:
                await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=3)
            except asyncio.TimeoutError:
                LOG.warning("xmpp_shutdown timed_out=true")

    async def _accept(self, reader, writer):
        address = writer.get_extra_info("peername")[0]
        if address != self.options.horizon_address or len(self.clients) >= 4:
            writer.close()
            await writer.wait_closed()
            return
        self.clients[writer] = asyncio.current_task()
        connection = writer.get_extra_info("socket")
        if connection is not None:
            try:
                connection.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                for name, seconds in (("TCP_KEEPIDLE", 30), ("TCP_KEEPINTVL", 10), ("TCP_KEEPCNT", 3)):
                    if hasattr(socket, name):
                        connection.setsockopt(socket.IPPROTO_TCP, getattr(socket, name), seconds)
            except OSError:
                LOG.debug("tcp_keepalive_customization_unavailable")
        opened = False
        parser = StreamParser()
        try:
            while True:
                if opened and not parser.incomplete:
                    data = await reader.read(4096)
                else:
                    data = await asyncio.wait_for(reader.read(4096), timeout=self.frame_timeout)
                if not data:
                    break
                for kind, value in parser.feed(data):
                    if kind == "close":
                        return
                    if kind == "open":
                        if (value.get("from") != self.options.horizon_jid
                                or value.get("to") != self.options.gateway_jid):
                            raise ValueError("Unexpected stream identity")
                        opened = True
                        writer.write(stream_header(self.options.gateway_jid, self.options.horizon_jid))
                        query = ET.Element("query", xmlns=DISCO)
                        writer.write(iq("get", "1", self.options.gateway_jid,
                                        self.options.horizon_jid, query))
                        LOG.info("xmpp_stream_open")
                    elif kind == "stanza":
                        self._stanza(value, writer)
                await asyncio.wait_for(writer.drain(), timeout=5)
        except (ValueError, OSError, asyncio.TimeoutError) as error:
            LOG.warning("xmpp_connection_closed reason=%s detail=%s", type(error).__name__, str(error)[:160])
        finally:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), timeout=2)
            except (OSError, asyncio.TimeoutError):
                pass
            self.clients.pop(writer, None)

    def _stanza(self, stanza, writer):
        if (stanza.get("from") != self.options.horizon_jid
                or stanza.get("to") != self.options.gateway_jid):
            raise ValueError("Unexpected stanza identity")
        if stanza.tag == f"{{{CLIENT}}}iq":
            kind = stanza.get("type")
            if kind in ("get", "set"):
                writer.write(read_response(stanza, self.options.gateway_jid,
                                           self.options.horizon_jid, self.options.gateway_name))
                command = next(iter(stanza), None)
                LOG.info("xmpp_request command=%s", command.tag if command is not None else "empty")
            elif kind == "result" and stanza.get("id") == "1":
                query = stanza.find(f"{{{DISCO}}}query")
                capabilities = [] if query is None else [
                    el.get("var") for el in query.findall(f"{{{DISCO}}}feature")]
                LOG.info("peer_capabilities capabilities=%s", capabilities)
            elif kind == "error":
                LOG.warning("xmpp_request_error id=%s", stanza.get("id"))
        elif stanza.tag == f"{{{CLIENT}}}message":
            event = decode_forward(stanza)
            self.received += 1
            self.on_telegram(event)

