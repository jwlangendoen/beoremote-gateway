"""Small setup UI behind Home Assistant ingress. No public configuration endpoint."""
import asyncio
import json
import logging
import os
import re
from pathlib import Path
import secrets

from aiohttp import ClientError, ClientSession, ClientTimeout, web

from .ha import HAError, HomeAssistant, USER_ID
from .sources import SourceError

LOG = logging.getLogger(__name__)

INGRESS_PEER = "172.30.32.2"


async def ingress_port():
    """Use the free ingress port allocated by Supervisor for host-network apps."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        # Standalone container checks have no Supervisor; access is still ingress-only.
        return 8099
    try:
        async with ClientSession(timeout=ClientTimeout(total=5), trust_env=False) as client:
            async with client.get("http://supervisor/addons/self/info", allow_redirects=False,
                                  headers={"Authorization": "Bearer " + token}) as response:
                if response.status != 200:
                    raise ValueError("Supervisor did not provide the setup page port")
                result = await response.json()
        port = result["data"]["ingress_port"]
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ValueError("Supervisor returned an invalid setup page port")
        return port
    except (ClientError, asyncio.TimeoutError, KeyError, TypeError):
        raise ValueError("Cannot read the setup page port from Supervisor; restart the app and check its log") from None


def make_app(controller, allowed_peers=frozenset({INGRESS_PEER}), admin_check=None):
    check_admin = admin_check or HomeAssistant().is_admin
    csrf = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(24)

    @web.middleware
    async def ingress_only(request, handler):
        # Check the TCP peer, not spoofable X-Forwarded-For/X-Real-IP headers.
        if request.remote not in allowed_peers:
            raise web.HTTPForbidden(text="Open this page through Home Assistant.")
        if request.method == "POST":
            if request.headers.get("X-Setup-Token") != csrf:
                raise web.HTTPForbidden(text="Reload the setup page and try again.")
            if request.content_type != "application/json":
                raise web.HTTPBadRequest(text="Expected JSON")
        try:
            # Supervisor replaces this header with its authenticated session user.
            # panel_admin controls navigation; it is not API authorization.
            user_id = request.headers.get("X-Remote-User-Id", "")
            if not USER_ID.fullmatch(user_id) or not await check_admin(user_id, fresh=request.method not in ("GET", "HEAD")):
                raise web.HTTPForbidden(text="Open this app as a Home Assistant administrator.")
            response = await handler(request)
        except ValueError as error:
            response = web.json_response({"error": str(error)}, status=400)
        except HAError as error:
            response = web.json_response({"error": str(error)}, status=503)
        except SourceError as error:
            response = web.json_response({"error": str(error), "code": error.code}, status=503)
        except OSError as error:
            LOG.warning("setup_request_failed reason=%s", type(error).__name__)
            response = web.json_response({"error": "Could not save settings. Check app storage and try again."}, status=503)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    app = web.Application(middlewares=[ingress_only], client_max_size=16384)

    async def index(request):
        path = request.headers.get("X-Ingress-Path", "")
        if (not path.startswith("/") or path.startswith("//")
                or any(char in path for char in "\\?#")
                or any(ord(char) < 33 for char in path)):
            path = ""
        page = Path(__file__).with_name("setup.html").read_text()
        # JSON strings embedded in script must not be able to close the script element.
        encode = lambda value: json.dumps(value).replace("<", "\\u003c")
        page = page.replace("__BASE_JSON__", encode(path.rstrip("/") + "/"))
        page = page.replace("__TOKEN_JSON__", encode(csrf)).replace("__NONCE__", nonce)
        return web.Response(text=page, content_type="text/html", headers={
            "Content-Security-Policy": "default-src 'none'; "
            f"script-src 'nonce-{nonce}'; style-src 'unsafe-inline'; connect-src 'self'; "
            "base-uri 'none'; frame-ancestors 'self'"})

    async def status(_request):
        return web.json_response(controller.status())

    async def devices(_request):
        if controller.options.mode != "auto":
            raise ValueError("Set Mode to auto in the app's Configuration tab and restart first.")
        try:
            return web.json_response({"devices": await controller.scan()})
        except (OSError, RuntimeError):
            return web.json_response({"error": "Discovery is unavailable. Check the local network and try again."}, status=503)

    async def select(request):
        data = await request.json()
        if not isinstance(data, dict) or set(data) != {"jid"} or not isinstance(data["jid"], str):
            raise ValueError("Choose a product from the discovered list.")
        await controller.select(data["jid"])
        return web.json_response(controller.status())

    async def pause(_request):
        await controller.pause()
        return web.json_response(controller.status())

    async def targets(_request):
        controller.action_tv()
        return web.json_response(await controller.actions.targets())

    async def actions(_request):
        return web.json_response({"actions": await controller.actions.list(controller.action_tv())})

    async def learn(_request):
        return web.json_response(await controller.start_learning())

    async def cancel(_request):
        await controller.cancel_learning()
        return web.json_response({"ok": True})

    async def fields(request, keys):
        data = await request.json()
        if not isinstance(data, dict) or set(data) != set(keys):
            raise ValueError("Reload the page and try again.")
        return data

    async def save(request):
        data = await fields(request, ("session_id", "name", "kind", "target"))
        return web.json_response(await controller.save_action(**data))

    async def toggle(request):
        data = await fields(request, ("id", "enabled"))
        await controller.toggle_action(data["id"], data["enabled"])
        return web.json_response({"ok": True})

    async def update(request):
        data = await fields(request, ("id", "name", "kind", "target"))
        return web.json_response(await controller.update_action(data["id"], data["name"], data["kind"], data["target"]))

    async def remove(request):
        data = await fields(request, ("id",))
        await controller.remove_action(data["id"])
        return web.json_response({"ok": True})

    async def source_options(request):
        data = await fields(request, ("enabled",))
        return web.json_response(await controller.set_sources_enabled(data["enabled"]))

    async def resume(request):
        await fields(request, ())
        await controller.resume()
        return web.json_response(controller.status())

    async def source_inventory(request):
        await fields(request, ())
        return web.json_response(await controller.inspect_sources())

    async def source_operation(request):
        operation = request.match_info["operation"]
        keys = {"install": ("retire_old",), "refresh": (), "targets": (), "save": ("revision", "entry"),
                "remove": ("revision", "id"), "restore": ("revision",), "test": ("id",),
                "reorder": ("revision", "source_list", "ids")}
        if operation not in keys:
            raise ValueError("Unknown TV source operation.")
        data = await fields(request, ("tv_jid", *keys[operation]))
        if operation == "install" and type(data["retire_old"]) is not bool:
            raise ValueError("Choose whether to replace the old helper.")
        if "revision" in data and (not isinstance(data["revision"], str) or len(data["revision"]) > 32):
            raise ValueError("Refresh the TV source setup first.")
        if "id" in data and (not isinstance(data["id"], str) or not re.fullmatch(r"BGW_[a-f0-9]{12}", data["id"])):
            raise ValueError("Choose a saved source.")
        if "entry" in data and not isinstance(data["entry"], dict):
            raise ValueError("Choose a valid source.")
        return web.json_response(await controller.source_operation(operation, data))

    app.add_routes([web.get("/", index), web.get("/api/status", status),
                    web.get("/api/devices", devices), web.post("/api/select", select),
                    web.post("/api/pause", pause), web.post("/api/resume", resume), web.get("/api/targets", targets),
                    web.get("/api/actions", actions), web.post("/api/learning/start", learn),
                    web.post("/api/learning/cancel", cancel), web.post("/api/actions/save", save),
                    web.post("/api/actions/update", update), web.post("/api/actions/toggle", toggle), web.post("/api/actions/remove", remove),
                    web.post("/api/sources/options", source_options), web.post("/api/sources/inventory", source_inventory),
                    web.post("/api/sources/{operation}", source_operation)])
    return app


async def start_web(controller, host="0.0.0.0", port=8099):
    runner = web.AppRunner(make_app(controller), access_log=None)
    try:
        await runner.setup()
        await web.TCPSite(runner, host, port).start()
    except BaseException:
        await runner.cleanup()
        raise
    return runner
