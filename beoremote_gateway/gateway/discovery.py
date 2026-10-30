"""Explicitly enabled native discovery, without Home Control advertising."""
import hashlib
import asyncio
import logging
import socket

from .protocol import discovery_txt

LOG = logging.getLogger(__name__)


def service_info(options):
    from zeroconf import ServiceInfo

    suffix = hashlib.sha256(options.gateway_jid.encode()).hexdigest()[:8]
    return ServiceInfo(
        "_beocore._tcp.local.",
        # Zeroconf splits dots into DNS labels on the wire. An instance must
        # occupy one label, so carry the dotted JID only in the TXT record.
        # Horizon's OnAddDevice explicitly supports an instance name != JID.
        f"BeoremoteGateway-{suffix}._beocore._tcp.local.",
        addresses=[socket.inet_aton(options.advertise_address)],
        port=options.xmpp_port,
        properties=discovery_txt(options.gateway_jid, options.gateway_name),
        server=f"beoremote-gateway-{suffix}.local.",
    )


class Announcer:
    def __init__(self, options):
        self.options = options
        self.zeroconf = None
        self.info = None
        self.advertised = False
        self.retries = 0

    async def start(self):
        from zeroconf import IPVersion
        from zeroconf.asyncio import AsyncZeroconf

        self.info = service_info(self.options)
        self.zeroconf = AsyncZeroconf(interfaces=[self.options.advertise_address],
                                    ip_version=IPVersion.V4Only)
        try:
            announcement = await self.zeroconf.async_register_service(self.info)
            await announcement
            self.advertised = True
        except BaseException:
            await self.zeroconf.async_close()
            self.zeroconf = None
            raise

    async def serve(self, stop, interval=60, retry_delay=1):
        delay = retry_delay
        try:
            while not stop.is_set():
                try:
                    if self.zeroconf is None:
                        await self.start()
                        LOG.info("gateway_advertised service=_beocore._tcp")
                    delay = retry_delay
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=interval)
                        break
                    except asyncio.TimeoutError:
                        announcement = await self.zeroconf.async_update_service(self.info)
                        await announcement
                except (OSError, RuntimeError) as error:
                    self.retries += 1
                    LOG.warning("gateway_discovery_retry reason=%s delay=%s", type(error).__name__, delay)
                    try:
                        await self.close()
                    except (OSError, RuntimeError):
                        LOG.warning("gateway_discovery_cleanup_failed")
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=delay)
                    except asyncio.TimeoutError:
                        pass
                    delay = min(delay * 2, 30)
        finally:
            await self.close()

    async def close(self):
        self.advertised = False
        if self.zeroconf is not None:
            try:
                goodbye = await self.zeroconf.async_unregister_service(self.info)
                await goodbye
            finally:
                await self.zeroconf.async_close()
                self.zeroconf = None

