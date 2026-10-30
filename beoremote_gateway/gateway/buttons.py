"""Suppress repeated LIGHT presses without swallowing a new press after release."""
from collections import OrderedDict
import time


class ButtonFilter:
    def __init__(self, clock=time.monotonic, hold_timeout=2.0, debounce=0.12,
                 commands=frozenset((0, 15, 37, 38, 39, 57))):
        self.clock = clock
        self.hold_timeout = hold_timeout
        self.debounce = debounce
        self.commands = commands
        self.pressed = OrderedDict()
        self.recent = OrderedDict()
        self.suppressed = 0

    @staticmethod
    def _remember(store, key, value):
        store[key] = value
        store.move_to_end(key)
        while len(store) > 32:
            store.popitem(last=False)

    def accept(self, event):
        raw = bytes.fromhex(event["data_hex"])
        if len(raw) != 13 or raw[1] != 27:
            return True
        key = (event["peer_jid"], event["originator"], raw[1])
        now = self.clock()
        if raw[4] == 126:
            self.pressed.pop(key, None)
            return True
        if raw[4] not in self.commands:
            return True
        previous = self.pressed.get(key)
        identity = (key, raw)
        repeated = previous is not None and previous[0] == raw and now - previous[1] < self.hold_timeout
        bounced = identity in self.recent and now - self.recent[identity] < self.debounce
        self._remember(self.pressed, key, (raw, now))
        if repeated or bounced:
            self.suppressed += 1
            return False
        self._remember(self.recent, identity, now)
        return True
