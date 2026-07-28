from dataclasses import dataclass


MISSING = object()
class InvalidValue(ValueError): pass
class DispatchError(Exception): pass
class ReactionCycleError(Exception): pass


@dataclass(frozen=True)
class Change:
    key: str
    old: object
    new: object


class _Tx:
    def __init__(self, store): self.store = store
    def __enter__(self): return self.store
    def __exit__(self, *args): return False


class Store:
    def __init__(self, initial=None): self.data = dict(initial or {}); self.ws = {}; self.n = 1
    def get(self, key, default=MISSING): return self.data.get(key, default)
    def snapshot(self): return dict(self.data)
    def watch(self, pattern, callback): self.ws[self.n] = (pattern, callback); self.n += 1; return self.n - 1
    def unwatch(self, token): return self.ws.pop(token, None) is not None
    def transaction(self): return _Tx(self)
    def set(self, key, value):
        old = self.data.get(key, MISSING); self.data[key] = value
        for pattern, cb in list(self.ws.values()):
            if pattern == "*" or pattern == key: cb(Change(key, old, value))
    def delete(self, key): self.data.pop(key, None)

