import unittest

try:
    import zeroconf
except ImportError:
    zeroconf = None

from gateway.config import Options
from gateway.discovery import service_info
from gateway.protocol import capability_hash


@unittest.skipIf(zeroconf is None, "Install runtime requirements to check discovery records")
class DiscoveryTests(unittest.TestCase):
    def test_instance_is_one_dns_label_and_jid_stays_in_txt(self):
        options = Options.from_dict({"mode": "advertise", "horizon_address": "192.0.2.10",
                                     "horizon_jid": "7980.1234567.12345678@products.bang-olufsen.com",
                                     "advertise_address": "192.0.2.20"})
        info = service_info(options)
        instance = info.name.removesuffix("._beocore._tcp.local.")
        self.assertNotIn(".", instance)
        self.assertLessEqual(len(instance.encode()), 63)
        self.assertEqual(info.properties[b"jid"].decode(), options.gateway_jid)
        self.assertEqual(info.properties[b"ver"].decode(), capability_hash())
        self.assertEqual(info.port, 5222)

    def test_friendly_name_change_preserves_instance_identity(self):
        first = Options(advertise_address="192.0.2.20")
        second = Options(advertise_address="192.0.2.20", gateway_name="Andere lichtnaam")
        self.assertEqual(service_info(first).name, service_info(second).name)

