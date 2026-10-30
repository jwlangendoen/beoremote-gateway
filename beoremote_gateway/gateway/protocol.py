"""BeoCore envelopes, based on read-only Horizon traces and native code."""
import base64
import binascii
import hashlib
import xml.etree.ElementTree as ET
from xml.sax.saxutils import quoteattr

CLIENT = "jabber:client"
STREAM = "http://etherx.jabber.org/streams"
DISCO = "http://jabber.org/protocol/disco#info"
PRODUCT = "beocore.product.1"
TUNNEL = "beocore.tunnel.1"
PING = "urn:xmpp:ping"
CAPABILITIES = (PRODUCT, TUNNEL, r"jid\20escaping")


def capability_hash(capabilities=CAPABILITIES):
    # Native code clones 0x17 bytes of 'client/product//beocore<'. This excludes
    # the final '<', unlike XEP-0115. Verified against the Horizon's mDNS hash.
    value = "client/product//beocore" + "".join(x + "<" for x in sorted(set(capabilities)))
    return base64.b64encode(hashlib.sha1(value.encode(), usedforsecurity=False).digest()).decode()


def discovery_txt(jid, name):
    return {"txtvers": "1", "node": "beocore", "hash": "sha-1",
            "jid": jid, "name": name, "ver": capability_hash()}


def stream_header(jid, peer):
    return (f'<stream:stream xmlns="{CLIENT}" xmlns:stream="{STREAM}" '
            f'version="1.0" from={quoteattr(jid)} to={quoteattr(peer)}>').encode()


def iq(kind, identifier, jid, peer, payload=None):
    element = ET.Element("iq", {"type": kind, "id": identifier, "from": jid, "to": peer})
    if payload is not None:
        element.append(payload)
    return ET.tostring(element, encoding="utf-8")


def disco_payload(name):
    query = ET.Element("query", xmlns=DISCO)
    ET.SubElement(query, "identity", category="client", type="product", name=name)
    for capability in sorted(CAPABILITIES):
        ET.SubElement(query, "feature", var=capability)
    return query


def contact_payload(name):
    # Minimal candidate metadata. TV acceptance still needs a real gateway test.
    command = ET.Element("GetContactInfo", xmlns=PRODUCT)
    contact = ET.SubElement(command, "contactInfo")
    ET.SubElement(contact, "name").text = name
    ET.SubElement(contact, "macs")
    ET.SubElement(contact, "sources")
    # roleCapability and integrated are optional in the native deserializer.
    return command


def read_response(request, jid, peer, name):
    kind, identifier = request.get("type"), request.get("id", "")
    if kind not in ("get", "set") or not identifier:
        raise ValueError("Expected an IQ request with an ID")
    payload = None
    supported = False
    if kind == "get" and request.find(f"{{{DISCO}}}query") is not None:
        payload, supported = disco_payload(name), True
    elif kind == "get" and request.find(f"{{{PING}}}ping") is not None:
        supported = True
    elif kind == "set" and request.find(f"{{{PRODUCT}}}GetContactInfo") is not None:
        if identifier.isascii() and identifier.isdecimal():
            payload, supported = contact_payload(name), True
    if supported:
        return iq("result", identifier, jid, peer, payload)
    error = ET.Element("error", type="cancel")
    ET.SubElement(error, "feature-not-implemented",
                  xmlns="urn:ietf:params:xml:ns:xmpp-stanzas")
    return iq("error", identifier, jid, peer, error)


def decode_forward(message):
    commands = message.findall(f"{{{CLIENT}}}body/{{{TUNNEL}}}Forward")
    if len(commands) != 1:
        raise ValueError("Expected exactly one tunnel Forward in message/body")
    command = commands[0]
    data = command.findtext(f"{{{TUNNEL}}}telegram/{{{TUNNEL}}}data") or ""
    timestamp_text = command.findtext(f"{{{TUNNEL}}}telegram/{{{TUNNEL}}}timestamp") or ""
    try:
        raw = base64.b64decode(data, validate=True)
        timestamp = int(timestamp_text)
    except (ValueError, binascii.Error) as error:
        raise ValueError("Invalid tunnel data or timestamp") from error
    if len(raw) != 13 or not 0 <= timestamp <= 0xFFFFFFFF:
        raise ValueError("Unexpected original telegram size or timestamp")
    return {"peer_jid": message.get("from"),
            "originator": command.findtext(f"{{{TUNNEL}}}originator") or "",
            "data_hex": raw.hex(), "data_base64": data, "timestamp": timestamp}

