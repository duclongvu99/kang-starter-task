"""Implement the public API from SPEC.md."""


class _Missing:
    def __repr__(self):
        return "MISSING"


MISSING = _Missing()


class InvalidValue(ValueError):
    pass


class DispatchError(Exception):
    pass


class ReactionCycleError(Exception):
    pass


class Change:
    pass


class Store:
    pass

