"""Local heartbeat and diagnostics, consumed by the container health check."""
import argparse
import asyncio
import json
import logging
import math
from pathlib import Path
import time
import tempfile

from . import __version__

LOG = logging.getLogger(__name__)
HEALTH_PATH = Path("/tmp/beoremote-gateway-health.json")


def check_health(path=HEALTH_PATH, now=None):
    try:
        if path.stat().st_size > 16384:
            return False
        state = json.loads(path.read_text())
        updated = state["updated_monotonic"]
        if type(updated) not in (int, float):
            return False
        age = (time.monotonic() if now is None else now) - updated
        return (state.get("version") == __version__ and state.get("healthy") is True
                and math.isfinite(age) and 0 <= age < 20)
    except (OSError, ValueError, TypeError, KeyError):
        return False


class HealthReporter:
    def __init__(self, snapshot, path=HEALTH_PATH, interval=5):
        self.snapshot = snapshot
        self.path = path
        self.interval = interval
        self.worker = None

    def write(self):
        state = {**self.snapshot(), "version": __version__, "updated_monotonic": time.monotonic()}
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=self.path.parent,
                                             prefix="." + self.path.name + "-", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(state, stream, separators=(",", ":"))
            temporary.replace(self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


    async def start(self):
        self.write()
        self.worker = asyncio.create_task(self._run(), name="health-heartbeat")

    async def _run(self):
        count = 0
        while True:
            await asyncio.sleep(self.interval)
            self.write()
            count += 1
            if count % 12 == 0:
                LOG.info("gateway_status %s", json.dumps(self.snapshot(), separators=(",", ":")))

    async def close(self):
        if self.worker is not None:
            self.worker.cancel()
            await asyncio.gather(self.worker, return_exceptions=True)
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            LOG.warning("health_cleanup_failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Local gateway health; no network access")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        raise SystemExit(0 if check_health() else 1)
    try:
        print(HEALTH_PATH.read_text())
    except OSError:
        print('{"healthy":false,"reason":"no heartbeat"}')
        raise SystemExit(1)
