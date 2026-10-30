"""Runtime options shared by the app and local development runner."""
from dataclasses import asdict, dataclass
import ipaddress
import re


def validate_jid(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+@[A-Za-z0-9.-]+", value):
        raise ValueError("JID must be a bare local peer identity without whitespace")
    if len(value.encode()) > 120:
        raise ValueError("JID is too long for peer metadata")


def validate_ipv4(value):
    if not isinstance(value, str):
        raise ValueError("IPv4 addresses must be strings")
    address = ipaddress.IPv4Address(value)
    if address.is_unspecified or address.is_multicast or str(address) == "255.255.255.255":
        raise ValueError("Expected a unicast IPv4 address")


@dataclass(frozen=True)
class Options:
    mode: str = "disabled"
    horizon_address: str = ""
    horizon_jid: str = ""
    advertise_address: str = ""
    gateway_name: str = "Home Assistant Licht"
    gateway_jid: str = "homeassistant.light.gateway@products.bang-olufsen.com"
    xmpp_port: int = 5222
    publish_ha_events: bool = False
    log_level: str = "info"

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("Options must be a JSON object")
        options = cls(**data)
        if options.mode not in ("disabled", "listen", "advertise"):
            raise ValueError("Unknown mode")
        if options.log_level not in ("debug", "info", "warning", "error"):
            raise ValueError("Unknown log level")
        if type(options.publish_ha_events) is not bool:
            raise ValueError("publish_ha_events must be a boolean")
        if type(options.xmpp_port) is not int or not 1 <= options.xmpp_port <= 65535:
            raise ValueError("xmpp_port must be between 1 and 65535")
        if not isinstance(options.gateway_name, str) or not 1 <= len(options.gateway_name) <= 64:
            raise ValueError("gateway_name must contain 1 to 64 characters")
        if not options.gateway_name.strip() or any(ord(char) < 32 for char in options.gateway_name):
            raise ValueError("gateway_name must contain visible text without control characters")
        validate_jid(options.gateway_jid)
        if options.mode != "disabled":
            validate_ipv4(options.horizon_address)
            validate_jid(options.horizon_jid)
            if options.horizon_jid == options.gateway_jid:
                raise ValueError("Gateway and Horizon need distinct identities")
        if options.mode == "advertise":
            validate_ipv4(options.advertise_address)
        return options

    def as_dict(self):
        return asdict(self)

