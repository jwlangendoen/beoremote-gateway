"""Bounded HA Core API requests through Supervisor. Credentials never reach the UI."""
import asyncio
import json
import os
import re
import time

from aiohttp import ClientError, ClientSession, ClientTimeout, ClientWSTimeout, TraceConfig

BASE = "http://supervisor/core/api/"
WS_URL = "http://supervisor/core/websocket"
USER_ID = re.compile(r"[0-9a-f]{32}")
MAX_BODY = 8 * 1024 * 1024


class HAError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class HomeAssistant:
    def __init__(self, token=None, clock=time.monotonic):
        self.token, self.clock = token, clock
        self._admin_cache = {}
        self._admin_lock = asyncio.Lock()

    async def is_admin(self, user_id, fresh=False):
        if not isinstance(user_id, str) or not USER_ID.fullmatch(user_id):
            return False
        async with self._admin_lock:
            cached = self._admin_cache.get(user_id)
            if not fresh and cached is not None and self.clock() < cached[0]:
                return cached[1]
            allowed = await self._lookup_admin(user_id)
            if user_id not in self._admin_cache and len(self._admin_cache) >= 32:
                self._admin_cache.pop(next(iter(self._admin_cache)))
            self._admin_cache[user_id] = (self.clock() + 15, allowed)
            return allowed

    async def _lookup_admin(self, user_id):
        token = self.token or os.environ.get("SUPERVISOR_TOKEN")
        if not token:
            raise HAError("Cannot verify Home Assistant administrator access.")
        trace = TraceConfig()
        async def reject_redirect(*_args):
            raise HAError("Home Assistant redirected the access check; access was denied.")
        trace.on_request_redirect.append(reject_redirect)
        try:
            async with asyncio.timeout(5):
                async with ClientSession(timeout=ClientTimeout(total=5), trust_env=False,
                                         trace_configs=[trace]) as client:
                    async with client.ws_connect(WS_URL, max_msg_size=MAX_BODY,
                            timeout=ClientWSTimeout(ws_receive=5, ws_close=1)) as socket:
                        challenge = await socket.receive_json()
                        if not isinstance(challenge, dict) or challenge.get("type") != "auth_required":
                            raise HAError("Cannot verify Home Assistant administrator access.")
                        await socket.send_json({"type": "auth", "access_token": token})
                        auth = await socket.receive_json()
                        if not isinstance(auth, dict) or auth.get("type") != "auth_ok":
                            raise HAError("Cannot verify Home Assistant administrator access.")
                        await socket.send_json({"id": 1, "type": "config/auth/list"})
                        result = await socket.receive_json()
            if (not isinstance(result, dict) or result.get("id") != 1
                    or result.get("type") != "result" or result.get("success") is not True
                    or not isinstance(result.get("result"), list)):
                raise HAError("Cannot verify Home Assistant administrator access.")
            for user in result["result"]:
                if isinstance(user, dict) and user.get("id") == user_id:
                    return (user.get("is_active") is True and (user.get("is_owner") is True
                            or isinstance(user.get("group_ids"), list) and "system-admin" in user["group_ids"]))
            return False
        except (ClientError, asyncio.TimeoutError, OSError, ValueError, TypeError):
            # Fail closed; never include credentials or user data in the error.
            raise HAError("Home Assistant is unavailable; administrator access could not be verified.") from None

    async def request(self, method, path, body=None):
        token = self.token or os.environ.get("SUPERVISOR_TOKEN")
        if not token:
            raise HAError("Open this app in Home Assistant to choose scenes and save actions.")
        try:
            async with ClientSession(timeout=ClientTimeout(total=10), trust_env=False) as client:
                async with client.request(method, BASE + path, json=body, allow_redirects=False,
                                          headers={"Authorization": "Bearer " + token}) as response:
                    if response.status == 404 and method == "GET":
                        return None
                    if response.status < 200 or response.status >= 300:
                        raise HAError("Home Assistant could not complete this request. Try again or check its log.", response.status)
                    parts, size = [], 0
                    async for chunk in response.content.iter_chunked(65536):
                        size += len(chunk)
                        if size > MAX_BODY:
                            raise HAError("Home Assistant's response is too large for this page.")
                        parts.append(chunk)
                    content = b"".join(parts)
                    return json.loads(content) if content else None
        except (ClientError, asyncio.TimeoutError, OSError, ValueError):
            # Never log the token, response body or an authenticated request URL.
            raise HAError("Home Assistant is unavailable. Your action has not been confirmed; try again.") from None

    async def states(self):
        states = await self.request("GET", "states")
        if not isinstance(states, list) or len(states) > 20000:
            raise HAError("Home Assistant did not return a usable list of scenes and lights.")
        return states
