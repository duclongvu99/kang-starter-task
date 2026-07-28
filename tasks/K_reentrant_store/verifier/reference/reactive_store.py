from __future__ import annotations

import math
from dataclasses import dataclass


class _Missing:
    __slots__ = ()

    def __repr__(self):
        return "MISSING"


MISSING = _Missing()


class InvalidValue(ValueError):
    pass


class DispatchError(Exception):
    def __init__(self, errors):
        self.errors = tuple(errors)
        super().__init__(f"{len(self.errors)} callback error(s)")


class ReactionCycleError(Exception):
    def __init__(self, pending_keys):
        self.pending_keys = tuple(pending_keys)
        super().__init__("reaction limit reached: " + ", ".join(self.pending_keys))


@dataclass(frozen=True)
class Change:
    key: str
    old: object
    new: object


def _clone(value):
    kind = type(value)
    if value is None or kind in (bool, int, str):
        return value
    if kind is float:
        if not math.isfinite(value):
            raise InvalidValue("float must be finite")
        return value
    if kind is list:
        return [_clone(item) for item in value]
    if kind is dict:
        result = {}
        for key, item in value.items():
            if type(key) is not str:
                raise InvalidValue("object keys must be strings")
            result[key] = _clone(item)
        return result
    raise InvalidValue("value is not finite JSON")


def _copy_maybe(value):
    return MISSING if value is MISSING else _clone(value)


def _same(left, right):
    if left is MISSING or right is MISSING:
        return left is right
    if type(left) is not type(right):
        return False
    if type(left) is list:
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    if type(left) is dict:
        return left.keys() == right.keys() and all(_same(left[k], right[k]) for k in left)
    return left == right


def _copy_state(state):
    return {key: _clone(value) for key, value in state.items()}


def _diff(before, after):
    changes = []
    for key in sorted(before.keys() | after.keys()):
        old = before.get(key, MISSING)
        new = after.get(key, MISSING)
        if not _same(old, new):
            changes.append(Change(key, _copy_maybe(old), _copy_maybe(new)))
    return changes


class _Transaction:
    def __init__(self, store):
        self.store = store
        self.entered = False

    def __enter__(self):
        if self.entered:
            raise RuntimeError("transaction context cannot be re-entered")
        self.entered = True
        store = self.store
        frame = (_copy_state(store._state), dict(store._watchers), store._next_token)
        store._frames.append(frame)
        store._depth += 1
        return store

    def __exit__(self, exc_type, exc, tb):
        store = self.store
        before, watchers, next_token = store._frames.pop()
        store._depth -= 1
        if exc_type is not None:
            store._state = before
            store._watchers = watchers
            store._next_token = next_token
            return False
        if store._depth == 0 and not store._dispatching:
            store._dispatch(_diff(before, store._state))
        return False


class Store:
    def __init__(self, initial=None):
        if initial is None:
            initial = {}
        if type(initial) is not dict:
            raise InvalidValue("initial state must be a plain dict")
        state = {}
        for key, value in initial.items():
            self._key(key)
            state[key] = _clone(value)
        self._state = state
        self._watchers = {}
        self._next_token = 1
        self._frames = []
        self._depth = 0
        self._dispatching = False

    @staticmethod
    def _key(key):
        if type(key) is not str or not key:
            raise InvalidValue("key must be a non-empty string")

    def get(self, key, default=MISSING):
        self._key(key)
        if key not in self._state:
            return default if default is MISSING else _clone(default)
        return _clone(self._state[key])

    def snapshot(self):
        return _copy_state(self._state)

    def set(self, key, value):
        self._key(key)
        owned = _clone(value)
        if key in self._state and _same(self._state[key], owned):
            return
        if self._depth or self._dispatching:
            self._state[key] = owned
            return
        before = _copy_state(self._state)
        self._state[key] = owned
        self._dispatch(_diff(before, self._state))

    def delete(self, key):
        self._key(key)
        if key not in self._state:
            return
        if self._depth or self._dispatching:
            del self._state[key]
            return
        before = _copy_state(self._state)
        del self._state[key]
        self._dispatch(_diff(before, self._state))

    def transaction(self):
        return _Transaction(self)

    def watch(self, pattern, callback):
        if type(pattern) is not str or not pattern:
            raise ValueError("pattern must be a non-empty string")
        if "*" in pattern[:-1] or pattern.endswith("**"):
            raise ValueError("invalid pattern")
        if not callable(callback):
            raise TypeError("callback must be callable")
        token = self._next_token
        self._next_token += 1
        self._watchers[token] = (pattern, callback)
        return token

    def unwatch(self, token):
        if token in self._watchers:
            del self._watchers[token]
            return True
        return False

    @staticmethod
    def _matches(pattern, key):
        return key.startswith(pattern[:-1]) if pattern.endswith("*") else key == pattern

    def _dispatch(self, wave):
        if not wave:
            return
        errors = []
        self._dispatching = True
        try:
            for wave_number in range(1, 33):
                wave_start = _copy_state(self._state)
                registry = sorted(self._watchers.items())
                for change in wave:
                    for _token, (pattern, callback) in registry:
                        if self._matches(pattern, change.key):
                            own_change = Change(
                                change.key, _copy_maybe(change.old), _copy_maybe(change.new)
                            )
                            try:
                                callback(own_change)
                            except BaseException as exc:
                                errors.append(exc)
                wave = _diff(wave_start, self._state)
                if not wave:
                    break
                if wave_number == 32:
                    raise ReactionCycleError(change.key for change in wave)
        finally:
            self._dispatching = False
        if errors:
            raise DispatchError(errors)

