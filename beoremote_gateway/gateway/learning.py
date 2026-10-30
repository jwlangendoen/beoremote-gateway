"""Capture an actual LIGHT press without forwarding that learning press to HA."""
import secrets
import time


def light_press(event):
    if event.get("originator") != "0":
        return None
    try:
        raw = bytes.fromhex(event.get("data_hex", ""))
    except (TypeError, ValueError):
        return None
    if (len(raw) != 13 or raw[:4] != bytes([0, 27, 0, 0]) or any(raw[5:])
            or raw[4] == 126):
        return None
    return raw.hex()


def button_name(payload):
    command = bytes.fromhex(payload)[4]
    functions = {15: 1, 37: 11, 38: 12, 39: 13, 57: 14}
    if command in functions:
        return f"LIGHT function {functions[command]}"
    return f"LIGHT {command}" if command <= 9 else "My LIGHT button"


class ButtonLearning:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.session = None
        self.tail = None

    def start(self, jid):
        self.finish()
        self.session = {"id": secrets.token_hex(16), "jid": jid,
                        "state": "listening", "until": self.clock() + 30}
        return self.status()

    def _current(self):
        if self.session is not None and self.clock() >= self.session["until"]:
            self.finish()
        return self.session

    def status(self):
        session = self._current()
        if session is None:
            return {"state": "idle"}
        result = {"id": session["id"], "state": session["state"],
                  "seconds_left": max(0, int(session["until"] - self.clock()))}
        if session["state"] == "captured":
            result["button_name"] = button_name(session["payload"])
        return result

    def capture(self, session_id, jid):
        session = self._current()
        if (session is None or session["id"] != session_id or session["jid"] != jid
                or session["state"] != "captured"):
            raise ValueError("Learn the LIGHT button again before saving.")
        return {"peer_jid": jid, "originator": "0", "data_hex": session["payload"]}

    def finish(self):
        self.session = None
        # Keep the held-button tail until release or two seconds of silence.

    def observe(self, event):
        now = self.clock()
        session = self._current()
        payload = light_press(event)
        if session is not None and event.get("peer_jid") == session["jid"]:
            if session["state"] == "listening":
                if payload is not None:
                    session.update(state="captured", payload=payload, until=now + 300)
                    self.tail = {"jid": session["jid"], "payload": payload, "last": now}
                # While listening, neither releases nor other remote messages go to HA.
                return False
            if payload == session["payload"]:
                self.tail = {"jid": session["jid"], "payload": payload, "last": now}
                return False
        if self.tail is not None:
            tail = self.tail
            if now - tail["last"] >= 2:
                self.tail = None
            elif event.get("peer_jid") == tail["jid"]:
                if event.get("originator") == "0" and event.get("data_hex") == "001b00007e0000000000000000":
                    self.tail = None
                    return False
                if payload == tail["payload"]:
                    tail["last"] = now
                    return False
                if payload is not None:
                    self.tail = None
        return True
