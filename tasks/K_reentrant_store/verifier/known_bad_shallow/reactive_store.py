from dataclasses import dataclass


MISSING = object()
class InvalidValue(ValueError): pass
class DispatchError(Exception):
    def __init__(self, errors): self.errors = tuple(errors)
class ReactionCycleError(Exception): pass


@dataclass(frozen=True)
class Change: key: str; old: object; new: object


class _Tx:
    def __init__(self, s): self.s=s; self.before=None
    def __enter__(self): self.before=dict(self.s.data); self.s.depth += 1; return self.s
    def __exit__(self, typ, exc, tb):
        self.s.depth -= 1
        if typ: self.s.data=self.before
        return False


class Store:
    def __init__(self, initial=None): self.data=dict(initial or {}); self.ws={}; self.n=1; self.depth=0
    def get(self,k,default=MISSING): return self.data.get(k,default)
    def snapshot(self): return dict(self.data)
    def set(self,k,v): self.data[k]=v
    def delete(self,k): self.data.pop(k,None)
    def transaction(self): return _Tx(self)
    def watch(self,p,cb): self.ws[self.n]=(p,cb); self.n+=1; return self.n-1
    def unwatch(self,t): return self.ws.pop(t,None) is not None

