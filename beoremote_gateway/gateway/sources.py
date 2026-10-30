"""Optional source setup: explicit, read-only ADB inventory for the selected TV."""
import asyncio
import json
import logging
import os
from pathlib import Path
import re
import socket
import tempfile

from aiohttp import ClientError, ClientSession, ClientTimeout

from .config import validate_ipv4

LOG = logging.getLogger(__name__)


async def matches_tv(address, jid):
    """Check native product identity before trusting a cached or rediscovered IP."""
    validate_ipv4(address)
    try:
        async with ClientSession(timeout=ClientTimeout(total=4), trust_env=False) as client:
            async with client.get(f"http://{address}:8080/BeoDevice", allow_redirects=False) as response:
                if response.status != 200:
                    return False
                raw = bytearray()
                async for chunk in response.content.iter_chunked(8192):
                    raw.extend(chunk)
                    if len(raw) > 65536:
                        return False
        product = json.loads(raw)["beoDevice"]["productId"]
        values = [product[name] for name in ("typeNumber", "itemNumber", "serialNumber")]
        if not all(isinstance(value, str) and re.fullmatch(r"[0-9]{1,20}", value) for value in values):
            return False
        return ".".join(values) + "@products.bang-olufsen.com" == jid
    except (ClientError, asyncio.TimeoutError, OSError, ValueError, KeyError, TypeError):
        return False


class SourceError(Exception):
    MESSAGES = {
        "adb_unavailable": "The ADB client is unavailable in this app installation.",
        "adb_timeout": "The TV did not answer in time. Check network ADB and try again.",
        "adb_output_limit": "The TV returned too much data. The inventory was stopped.",
        "adb_command_failed": "The ADB check failed. Check the TV authorization and try again.",
    }

    def __init__(self, code):
        self.code = code
        super().__init__(self.MESSAGES.get(code, "The TV connection could not be checked."))


class SourceSettings:
    def __init__(self, directory, adb=None):
        self.path = Path(directory) / "source-management.json"
        self.adb = adb if adb is not None else AdbInventory(directory)
        self.verify = matches_tv
        self.enabled = False
        self.error = ""
        self.lock = asyncio.Lock()
        try:
            if self.path.exists():
                if self.path.stat().st_size > 4096:
                    raise ValueError("Invalid source preferences")
                data = json.loads(self.path.read_text())
                if not isinstance(data, dict) or set(data) != {"enabled"} or type(data["enabled"]) is not bool:
                    raise ValueError("Invalid source preferences")
                self.enabled = data["enabled"]
        except (OSError, ValueError):
            self.error = "Saved source preferences could not be read. Choose the option again."
            LOG.warning("source_preferences_unavailable")

    def status(self):
        return {"enabled": self.enabled, "error": self.error}

    async def set_enabled(self, enabled):
        if type(enabled) is not bool:
            raise ValueError("Choose whether to enable source management.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=self.path.parent,
                                             prefix="." + self.path.name + "-", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump({"enabled": enabled}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self.enabled, self.error = enabled, ""
        if not enabled:
            await self.close()

    async def close(self):
        try:
            await self.adb.close()
        except (OSError, SourceError):
            LOG.warning("source_adb_cleanup_failed")


def packages(all_packages, system_packages):
    """Package IDs only: inventory does not imply launchability or remote support."""
    def parse(output):
        return {line.removeprefix("package:").strip() for line in output.splitlines()
                if re.fullmatch(r"package:[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+", line.strip())}

    system = parse(system_packages)
    return [{"package": package, "name": package, "system": package in system}
            for package in sorted(parse(all_packages), key=lambda p: (p in system, p.lower()))]


class AdbInventory:
    """Own loopback ADB server, persistent key, fixed read-only shell commands.

    No shell command or package name is accepted from an HTTP request. Connecting
    may prompt for authorization on the TV; inventory never opens an activity.
    """
    def __init__(self, directory, binary="adb"):
        self.directory = Path(directory) / "adb" / ".android"
        self.binary = binary
        self.port = None

    async def _command(self, *arguments, timeout=8, check=True):
        # The container also links ADB's default key directory into /data:
        # Debian's older client ignores the newer Android directory variables.
        # This prevents an ephemeral default key being offered after an update.
        environment = {key: value for key, value in os.environ.items()
                       if key not in {"ADB_SERVER_SOCKET", "ANDROID_ADB_SERVER_PORT", "ADB_SERVER_PORT"}}
        environment.update({"ADB_VENDOR_KEYS": str(self.directory / "adbkey"),
                       "ANDROID_USER_HOME": str(self.directory),
                       "ANDROID_SDK_HOME": str(self.directory.parent)})
        try:
            process = await asyncio.create_subprocess_exec(
                self.binary, *arguments, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT, env=environment)
        except FileNotFoundError:
            raise SourceError("adb_unavailable") from None
        try:
            # Bound output as well as time: a broken peer must not fill memory.
            async def collect():
                output = bytearray()
                while chunk := await process.stdout.read(16384):
                    output.extend(chunk)
                    if len(output) > 2 * 1024 * 1024:
                        raise SourceError("adb_output_limit")
                await process.wait()
                return output.decode("utf-8", errors="replace")
            output = await asyncio.wait_for(collect(), timeout)
        except BaseException as error:
            if process.returncode is None:
                process.kill()
            await process.wait()
            if isinstance(error, asyncio.TimeoutError):
                action = next((name for name in ("keygen", "start-server", "connect", "devices", "getprop", "packages", "kill-server")
                               if name in arguments), "unknown")
                LOG.warning("source_adb_timeout action=%s", action)
                raise SourceError("adb_timeout") from None
            raise
        if check and process.returncode:
            # Do not surface raw subprocess output, device identities or paths.
            raise SourceError("adb_command_failed")
        return output

    async def _start(self):
        if self.port is not None:
            return
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory.parent.chmod(0o700)
        self.directory.chmod(0o700)
        key = self.directory / "adbkey"
        if not key.exists():
            await self._command("keygen", str(key))
        key.chmod(0o600)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        # Debian's ADB treats numeric loopback as a remote host and refuses to
        # auto-start a server there. Its local-server spelling is 'localhost'.
        await self._command("-L", f"tcp:localhost:{port}", "start-server")
        self.port = port

    async def inspect(self, address):
        validate_ipv4(address)
        await self._start()
        serial = f"{address}:5555"
        prefix = ("-P", str(self.port))
        try:
            await self._command(*prefix, "connect", serial, check=False, timeout=3)
        except SourceError as error:
            if error.code != "adb_timeout":
                raise
            # The server may be waiting for a TV authorization prompt. Query
            # the transport state even when the connect client times out.
        devices = await self._command(*prefix, "devices")
        states = dict(line.split()[:2] for line in devices.splitlines()
                      if len(line.split()) >= 2 and line.split()[0] == serial)
        state = states.get(serial)
        if state != "device":
            return {"state": "authorization_required" if state == "unauthorized" else "unreachable", "apps": []}
        target = (*prefix, "-s", serial, "shell")
        model = (await self._command(*target, "getprop", "ro.product.model")).strip()[:128]
        android = (await self._command(*target, "getprop", "ro.build.version.release")).strip()[:64]
        installed = await self._command(*target, "pm", "list", "packages")
        system = await self._command(*target, "pm", "list", "packages", "-s")
        return {"state": "connected", "model": model, "android": android,
                "apps": packages(installed, system)}

    async def close(self):
        if self.port is not None:
            try:
                await self._command("-P", str(self.port), "kill-server", timeout=3)
            finally:
                self.port = None
