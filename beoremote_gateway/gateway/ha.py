"""Bounded HA Core API requests through Supervisor. Credentials never reach the UI."""
import asyncio
import json
import os

from aiohttp import ClientError, ClientSession, ClientTimeout

BASE = "http://supervisor/core/api/"
MAX_BODY = 8 * 1024 * 1024


class HAError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class HomeAssistant:
    def __init__(self, token=None):
        self.token = token

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
