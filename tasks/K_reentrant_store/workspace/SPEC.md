# Specification

Implement the following public API in `reactive_store.py`:

```python
MISSING                         # one exported singleton

@dataclass(frozen=True)
class Change:
    key: str
    old: object                 # MISSING when absent
    new: object                 # MISSING when absent

class InvalidValue(ValueError): ...
class DispatchError(Exception):
    errors: tuple[BaseException, ...]
class ReactionCycleError(Exception):
    pending_keys: tuple[str, ...]

class Store:
    def __init__(self, initial: dict[str, object] | None = None): ...
    def get(self, key, default=MISSING): ...
    def snapshot(self) -> dict: ...
    def set(self, key: str, value: object) -> None: ...
    def delete(self, key: str) -> None: ...
    def transaction(self): ...                 # context manager
    def watch(self, pattern: str, callback) -> int: ...
    def unwatch(self, token: int) -> bool: ...
```

## Values, ownership, and patterns

- Keys and patterns are non-empty strings.
- Values are finite JSON values: `None`, exact `bool`, exact `int`, finite exact
  `float`, `str`, lists of values, and dicts with string keys and valid values.
  Cycles, tuples, subclasses, NaN, and infinities raise `InvalidValue` before
  any state change.
- The store owns deep copies.  Mutating an input, a `get`/`snapshot` result, or
  a `Change` value can never mutate the store or another callback's `Change`.
- A pattern is either an exact key (`"user.name"`) or a prefix ending in exactly
  one `*` (`"user.*"`).  Prefix matching is literal, so this example matches
  `"user.name"` but not `"users.name"`.  Invalid patterns/callbacks raise before
  registration.
- Watch tokens are increasing positive integers.  `unwatch` returns whether the
  token existed.

## Transactions and savepoints

Every `set` or `delete` outside an explicit transaction is its own transaction.
Entering `transaction()` creates a savepoint containing state, watcher
registry, and next-token value.

- Normal exit keeps the changes.  Only exit of the outermost transaction starts
  notification.
- Exceptional exit restores that savepoint completely and propagates the same
  exception.  Thus an inner failure can be caught by outer code without losing
  earlier outer changes, while an outer failure rolls everything back,
  including watch/unwatch operations and token allocation.
- Changes are coalesced against the outermost entry state.  A key restored to
  its original value produces no notification.  Events are sorted by key.
- `delete` of an absent key and `set` to a deeply equal value are no-ops.

## Deterministic notification waves

For every non-empty commit, dispatch proceeds in waves:

1. Freeze a snapshot of the watcher registry and state at wave start.
2. Deliver that wave's `Change` events in sorted-key order.  For each event,
   call matching watchers from the frozen registry in ascending token order.
   Every call receives its own deep-copied `Change`.
3. Callbacks may call every Store API, including nested transactions and
   watch/unwatch.  They never dispatch recursively.  After all callbacks in the
   wave, diff current state against the wave-start state; that sorted diff is
   the next wave.  A value changed and restored within a wave emits nothing.
4. Watcher additions/removals during a wave affect the next wave only.  If no
   next state wave exists, they receive nothing for the completed commit.

If a callback raises, record the exception and continue with all remaining
callbacks and waves.  State/watch changes committed before it raised remain.
After quiescence, raise one `DispatchError` whose `errors` tuple contains the
original exception objects in invocation order.  (An explicit transaction
inside the callback still follows normal rollback rules if its body raises.)

At most 32 non-empty waves are delivered for one outer commit.  If wave 32
creates another non-empty diff, retain all state and registry changes through
wave 32 and raise `ReactionCycleError` without delivering wave 33;
`pending_keys` is the sorted tuple of that pending diff's keys.  This error takes
precedence over a `DispatchError` from earlier waves.

Calls made while dispatching join the current wave calculation.  Once dispatch
ends (normally or with either dispatch error), the store is usable for later
independent transactions.

The hidden tests use only the behavior specified here and impose a 60-second
total budget.  No filesystem, network, threads, timing, or introspection is
needed.

