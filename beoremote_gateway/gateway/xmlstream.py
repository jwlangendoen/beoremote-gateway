"""Bounded incremental XML stream parser; no DTDs or entity declarations."""
import xml.etree.ElementTree as ET
from xml.parsers import expat

from .protocol import STREAM


class StreamParser:
    def __init__(self):
        self.parser = expat.ParserCreate(namespace_separator="}")
        # Recent Expat versions defer reparsing fragmented tokens. For this
        # bounded stream that can postpone a complete stanza until another
        # packet arrives, stalling the handshake. Keep delivery immediate.
        if hasattr(self.parser, "SetReparseDeferralEnabled"):
            self.parser.SetReparseDeferralEnabled(False)
        self.parser.StartElementHandler = self._start
        self.parser.EndElementHandler = self._end
        self.parser.CharacterDataHandler = self._text
        self.parser.StartDoctypeDeclHandler = self._forbid
        self.parser.EntityDeclHandler = self._forbid
        self.parser.ExternalEntityRefHandler = self._forbid
        self.depth = 0
        self.stack = []
        self.events = []
        self.total = 0
        self.boundary = 0

    @staticmethod
    def _tag(name):
        return "{" + name if "}" in name else name

    @staticmethod
    def _forbid(*_):
        raise ValueError("XML declarations and external entities are unsupported")

    def _start(self, name, attributes):
        self.depth += 1
        if self.depth > 24 or len(attributes) > 32:
            raise ValueError("XML nesting or attribute limit exceeded")
        if self.depth == 1:
            if self._tag(name) != f"{{{STREAM}}}stream":
                raise ValueError("Expected an XMPP stream")
            self.events.append(("open", attributes))
            self.boundary = self.parser.CurrentByteIndex
            return
        element = ET.Element(self._tag(name), attributes)
        if self.stack:
            self.stack[-1].append(element)
        self.stack.append(element)

    def _end(self, _):
        if self.depth == 1:
            self.events.append(("close", None))
        else:
            element = self.stack.pop()
            if self.depth == 2:
                self.events.append(("stanza", element))
                self.boundary = self.parser.CurrentByteIndex
        self.depth -= 1

    def _text(self, value):
        if self.stack:
            element = self.stack[-1]
            element.text = (element.text or "") + value

    def feed(self, data):
        self.total += len(data)
        if self.total - self.boundary > 65536:
            raise ValueError("XML stanza limit exceeded")
        try:
            self.parser.Parse(data, False)
        except expat.ExpatError as error:
            raise ValueError("Invalid XML stream") from error
        events, self.events = self.events, []
        return events

    @property
    def incomplete(self):
        return self.depth > 1 or self.parser.CurrentByteIndex < self.total

