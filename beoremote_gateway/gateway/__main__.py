"""App entry point. Defaults to no listening, discovery or HA events."""
import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
import signal

from .config import Options
from . import __version__
from .buttons import ButtonFilter
from .discovery import Announcer
from .events import EventPublisher
from .health import HEALTH_PATH, HealthReporter
from .protocol import discovery_txt
from .server import GatewayServer

LOG = logging.getLogger(__name__)


async def run(options, stop, health_path=HEALTH_PATH):
    publisher = server = announcer = discovery_task = None
    buttons = ButtonFilter()

    def status():
        listening = server is not None and server.server is not None and server.server.is_serving()
        workers_ok = ((publisher is None or publisher.worker is not None and not publisher.worker.done())
                      and (discovery_task is None or not discovery_task.done()))
        return {"healthy": options.mode == "disabled" or bool(listening and workers_ok),
                "mode": options.mode, "listener": bool(listening),
                "discovery": bool(announcer is not None and announcer.advertised),
                "peers": 0 if server is None else len(server.clients),
                "received": 0 if server is None else server.received,
                "suppressed": buttons.suppressed,
                "ha": {"delivery": "disabled"} if publisher is None else publisher.status()}

    health = HealthReporter(status, path=health_path)

    def telegram(event):
        LOG.debug("telegram %s", json.dumps(event, separators=(",", ":")))
        if publisher is not None and buttons.accept(event):
            publisher.submit(event)

    try:
        LOG.info("gateway_starting version=%s mode=%s ha_events=%s", __version__, options.mode, options.publish_ha_events)
        if options.mode == "disabled":
            LOG.info("gateway_disabled")
            await health.start()
            await stop.wait()
            return
        publisher = EventPublisher(os.environ.get("SUPERVISOR_TOKEN")) if options.publish_ha_events else None
        if publisher is not None:
            await publisher.start()
        server = GatewayServer(options, telegram)
        await server.start()
        if options.mode == "advertise":
            announcer = Announcer(options)
            discovery_task = asyncio.create_task(announcer.serve(stop), name="discovery-maintenance")
        await health.start()
        await stop.wait()
    finally:
        await health.close()
        try:
            if discovery_task is not None:
                discovery_task.cancel()
                await asyncio.gather(discovery_task, return_exceptions=True)
        finally:
            if server is not None:
                await server.close()
            if publisher is not None:
                await publisher.close()
        LOG.info("gateway_stopped")


async def main(options):
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop.set)
    await run(options, stop)


def cli():
    parser = argparse.ArgumentParser(description="Experimental Beoremote gateway receiver")
    parser.add_argument("--options", type=Path)
    parser.add_argument("--check", action="store_true", help="Validate and print candidate TXT; no network")
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        options = Options.from_dict(json.loads(arguments.options.read_text()) if arguments.options else {})
        logging.getLogger().setLevel(options.log_level.upper())
        if arguments.check:
            print(json.dumps({"mode": options.mode, "publish_ha_events": options.publish_ha_events,
                              "candidate_txt": discovery_txt(options.gateway_jid, options.gateway_name)}, indent=2))
        else:
            asyncio.run(main(options))
    except (ValueError, TypeError, OSError) as error:
        LOG.error("gateway_start_failed reason=%s", str(error))
        raise SystemExit(1) from None


if __name__ == "__main__":
    cli()
