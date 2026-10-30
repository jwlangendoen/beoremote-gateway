"""One running receiver. Reconfiguration always closes the previous receiver first."""
import asyncio
import json
import logging
import os

from .buttons import ButtonFilter
from .discovery import Announcer
from .events import EventPublisher
from .server import GatewayServer

LOG = logging.getLogger(__name__)


class GatewayRuntime:
    def __init__(self, options):
        self.options = options
        self.publisher = self.server = self.announcer = self.discovery_task = None
        self.buttons = ButtonFilter()
        self.observer = None
        self.stop = asyncio.Event()

    def telegram(self, event):
        LOG.debug("telegram %s", json.dumps(event, separators=(",", ":")))
        if self.observer is not None and self.observer(event) is False:
            return
        if self.publisher is not None and self.buttons.accept(event):
            self.publisher.submit(event)

    async def start(self):
        try:
            if self.options.publish_ha_events:
                self.publisher = EventPublisher(os.environ.get("SUPERVISOR_TOKEN"))
                await self.publisher.start()
            self.server = GatewayServer(self.options, self.telegram)
            await self.server.start()
            if self.options.mode == "advertise":
                self.announcer = Announcer(self.options)
                self.discovery_task = asyncio.create_task(self.announcer.serve(self.stop))
        except BaseException:
            await self.close()
            raise

    def snapshot(self):
        listening = self.server is not None and self.server.server is not None and self.server.server.is_serving()
        workers_ok = ((self.publisher is None or self.publisher.worker is not None and not self.publisher.worker.done())
                      and (self.discovery_task is None or not self.discovery_task.done()))
        return {"healthy": bool(listening and workers_ok), "listener": bool(listening),
                "discovery": bool(self.announcer is not None and self.announcer.advertised),
                "peers": 0 if self.server is None else len(self.server.clients),
                "received": 0 if self.server is None else self.server.received,
                "suppressed": self.buttons.suppressed,
                "ha": {"delivery": "disabled"} if self.publisher is None else self.publisher.status()}

    async def close(self):
        self.stop.set()
        try:
            if self.discovery_task is not None:
                self.discovery_task.cancel()
                await asyncio.gather(self.discovery_task, return_exceptions=True)
        finally:
            try:
                if self.server is not None:
                    await self.server.close()
            finally:
                if self.publisher is not None:
                    await self.publisher.close()
