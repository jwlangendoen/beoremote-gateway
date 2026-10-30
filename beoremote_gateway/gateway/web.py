"""Small setup UI behind Home Assistant ingress. No public configuration endpoint."""
import asyncio
import json
import os
from pathlib import Path
import secrets

from aiohttp import ClientError, ClientSession, ClientTimeout, web

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


def make_app(controller, allowed_peers=frozenset({INGRESS_PEER})):
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
            response = await handler(request)
        except ValueError as error:
            response = web.json_response({"error": str(error)}, status=400)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    app = web.Application(middlewares=[ingress_only], client_max_size=16384)

    async def index(request):
        path = request.headers.get("X-Ingress-Path", "")
        if not path.startswith("/") or path.startswith("//"):
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

    app.add_routes([web.get("/", index), web.get("/api/status", status),
                    web.get("/api/devices", devices), web.post("/api/select", select),
                    web.post("/api/pause", pause)])
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
