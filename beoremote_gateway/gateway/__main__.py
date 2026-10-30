"""App entry point with a Home Assistant ingress setup page."""
import argparse
import asyncio
import json
import logging
from pathlib import Path
import signal

from .config import Options
from . import __version__
from .health import HEALTH_PATH, HealthReporter
from .protocol import discovery_txt
from .setup import SETUP_PATH, SetupController

LOG = logging.getLogger(__name__)


async def run(options, stop, health_path=HEALTH_PATH, setup_path=SETUP_PATH, web_port=None):
    controller = SetupController(options, path=setup_path)
    health = HealthReporter(controller.snapshot, path=health_path)
    web_runner = None
    try:
        LOG.info("gateway_starting version=%s mode=%s ha_events=%s", __version__, options.mode, options.publish_ha_events)
        await controller.start()
        if web_port is not None:
            from .web import start_web
            web_runner = await start_web(controller, port=web_port)
            LOG.info("setup_ui_ready ingress_only=true")
        await health.start()
        await stop.wait()
    finally:
        await health.close()
        try:
            if web_runner is not None:
                await web_runner.cleanup()
        finally:
            await controller.close()
        LOG.info("gateway_stopped")


async def main(options):
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop.set)
    from .web import ingress_port
    await run(options, stop, web_port=await ingress_port())


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
