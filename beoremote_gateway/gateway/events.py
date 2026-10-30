"""Optional raw HA events. No HA action/service calls are implemented."""
import asyncio
import json
import logging
import time
import urllib.request

LOG = logging.getLogger(__name__)
EVENT_URL = "http://supervisor/core/api/events/beoremote_telegram"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


class EventPublisher:
    def __init__(self, token, clock=time.monotonic, max_age=2.0, queue_size=32, wall_clock=time.time):
        if not token:
            raise ValueError("SUPERVISOR_TOKEN is required to publish HA events")
        self.token = token
        self.clock = clock
        self.wall_clock = wall_clock
        self.max_age = max_age
        self.queue = asyncio.Queue(maxsize=queue_size)
        self.worker = None
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)
        self.published = self.failed = self.dropped = self.expired = 0
        self.last_result = "idle"
        self.last_warning = float("-inf")

    async def start(self):
        self.worker = asyncio.create_task(self._run())

    def submit(self, event):
        try:
            payload = {**event, "received_at": self.wall_clock()}
            self.queue.put_nowait((self.clock(), payload))
        except asyncio.QueueFull:
            self.dropped += 1
            self._warning("queue_full")

    def _warning(self, reason):
        now = self.clock()
        if now - self.last_warning >= 30:
            LOG.warning("ha_event_unavailable reason=%s failed=%s dropped=%s expired=%s",
                        reason, self.failed, self.dropped, self.expired)
            self.last_warning = now

    def _post(self, event):
        request = urllib.request.Request(
            EVENT_URL, data=json.dumps(event).encode(), method="POST",
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
        with self.opener.open(request, timeout=1) as response:
            if response.status not in (200, 201):
                raise ValueError("Unexpected HA event response")

    async def _run(self):
        while True:
            received, event = await self.queue.get()
            try:
                if self.clock() - received >= self.max_age:
                    self.expired += 1
                    self._warning("stale")
                    continue
                # Never retry an ambiguous POST: HA may already have acted.
                await asyncio.to_thread(self._post, event)
                if self.last_result == "unavailable":
                    LOG.info("ha_event_delivery_recovered")
                self.last_result = "ok"
                self.published += 1
            except Exception as error:
                self.failed += 1
                self.last_result = "unavailable"
                self._warning(type(error).__name__)
            finally:
                self.queue.task_done()

    async def close(self):
        if self.worker is not None:
            try:
                await asyncio.wait_for(self.queue.join(), timeout=2)
            except asyncio.TimeoutError:
                LOG.warning("ha_event_shutdown pending=%s", self.queue.qsize())
            self.worker.cancel()
            await asyncio.gather(self.worker, return_exceptions=True)

    def status(self):
        return {"delivery": self.last_result, "queue": self.queue.qsize(),
                "published": self.published, "failed": self.failed,
                "dropped": self.dropped, "expired": self.expired}

