MISSING = object()
class InvalidValue(ValueError): pass
class DispatchError(Exception): pass
class ReactionCycleError(Exception): pass
class Change: pass


class Store:
    def __init__(self, initial=None): self.data = dict(initial or {})
    def get(self, key, default=MISSING): return self.data.get(key, default)
    def snapshot(self): return dict(self.data)
    def set(self, key, value): self.data[key] = value
    def delete(self, key): self.data.pop(key, None)
    def watch(self, pattern, callback): return 1
    def unwatch(self, token): return False
    def transaction(self): return self
    def __enter__(self): return self
    def __exit__(self, *args): return False

