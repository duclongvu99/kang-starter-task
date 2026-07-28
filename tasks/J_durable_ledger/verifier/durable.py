"""Public deterministic storage model for Task J.

Candidate code may use only the five public methods on DurableDisk.  The extra
helpers are for constructing local examples and for the hidden crash checker.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy


class InvalidRecord(ValueError):
    pass


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def encode_state(state: dict) -> bytes:
    payload = canonical_json(state)
    envelope = {
        "payload": payload,
        "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }
    return canonical_json(envelope).encode("utf-8")


def decode_state(data: bytes) -> dict:
    try:
        envelope = json.loads(bytes(data).decode("utf-8"))
        if set(envelope) != {"payload", "sha256"}:
            raise ValueError
        payload = envelope["payload"]
        digest = envelope["sha256"]
        if not isinstance(payload, str) or not isinstance(digest, str):
            raise ValueError
        if hashlib.sha256(payload.encode("utf-8")).hexdigest() != digest:
            raise ValueError
        state = json.loads(payload)
        if not isinstance(state, dict) or set(state) != {"accounts", "applied"}:
            raise ValueError
        if not isinstance(state["accounts"], dict) or not isinstance(state["applied"], dict):
            raise ValueError
        return state
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
        raise InvalidRecord("corrupt durable record") from exc


class DurableDisk:
    """Two-slot disk.  Normal execution records all possible crash images."""

    __slots__ = ("_durable", "_volatile", "_head", "_trace", "_mutations")

    def __init__(self, image: dict):
        self._durable = {
            "a": None if image["slots"].get("a") is None else bytes(image["slots"]["a"]),
            "b": None if image["slots"].get("b") is None else bytes(image["slots"]["b"]),
        }
        self._volatile = dict(self._durable)
        self._head = image["head"]
        self._trace = []
        self._mutations = 0

    def read_head(self):
        return self._head

    def read_slot(self, name):
        self._check_name(name)
        value = self._volatile[name]
        return None if value is None else bytes(value)

    def write_slot(self, name, data):
        self._check_name(name)
        if not isinstance(data, bytes):
            raise TypeError("slot data must be bytes")
        if len(data) > 65_536:
            raise ValueError("slot exceeds 65,536 bytes")
        self._record_current("before:write_slot")
        self._volatile[name] = bytes(data)
        self._mutations += 1
        self._record_current("after:write_slot")

    def flush_slot(self, name):
        self._check_name(name)
        new = self._volatile[name]
        if new is None:
            raise ValueError("cannot flush an empty slot")
        old = self._durable[name]
        self._record_current("before:flush_slot")
        old_bytes = old or b""
        width = max(len(old_bytes), len(new))
        cuts = {0, 1, width // 4, width // 2, (3 * width) // 4, max(0, width - 1), width}
        for cut in sorted(cuts):
            torn = new[:cut] + old_bytes[cut:]
            if cut >= len(new):
                torn = bytes(new)
            image = self._image_with(name, torn)
            self._trace.append({"where": f"during:flush_slot:{cut}", "image": image})
        self._durable[name] = bytes(new)
        self._mutations += 1
        self._record_current("after:flush_slot")

    def publish(self, name):
        self._check_name(name)
        self._record_current("before:publish")
        self._head = name
        self._mutations += 1
        self._record_current("after:publish")

    @staticmethod
    def _check_name(name):
        if name not in ("a", "b"):
            raise ValueError("slot name must be 'a' or 'b'")

    def _image_with(self, name, value):
        slots = dict(self._durable)
        slots[name] = value
        return {"head": self._head, "slots": slots}

    def _record_current(self, where):
        self._trace.append({"where": where, "image": self.image()})

    def image(self):
        return {"head": self._head, "slots": deepcopy(self._durable)}

    def crash_images(self):
        unique = []
        seen = set()
        for record in self._trace:
            image = record["image"]
            key = (image["head"], image["slots"]["a"], image["slots"]["b"])
            if key not in seen:
                seen.add(key)
                unique.append({"where": record["where"], "image": deepcopy(image)})
        return unique

    @property
    def mutation_count(self):
        return self._mutations


def make_image(state: dict, head: str = "a") -> dict:
    other = "b" if head == "a" else "a"
    return {"head": head, "slots": {head: encode_state(state), other: None}}
