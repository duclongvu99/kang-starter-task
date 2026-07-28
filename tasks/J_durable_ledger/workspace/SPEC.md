# Specification

Implement these functions and exception classes in `solution.py`:

```python
class TransactionRejected(ValueError): ...
class TransactionConflict(ValueError): ...

def recover(disk) -> dict: ...
def apply(disk, txid: str, changes: dict[str, int]) -> None: ...
```

## State and input rules

`recover` returns a fresh object of this exact shape:

```python
{"accounts": {"alice": 100, "bob": 50},
 "applied": {"tx-1": "<64 lower-case hex characters>"}}
```

The fingerprint is
`sha256(canonical_json(changes).encode()).hexdigest()`.  `canonical_json` is
exported by `durable.py`.

A new transaction is valid only when all of these hold:

1. `txid` is a string matching `[A-Za-z0-9._-]{1,64}`.
2. `changes` is a non-empty plain `dict`; every key is an existing account
   name; every value is a non-zero `int` but not a `bool`.
3. The deltas sum to zero and no resulting balance is negative.

Invalid input raises `TransactionRejected` and performs **zero disk mutations**.
If `txid` was already applied with the same fingerprint, `apply` is a no-op and
performs zero disk mutations.  Reusing it with a different fingerprint raises
`TransactionConflict`, again with zero disk mutations.

## Device model

Use only this public interface from `durable.py`:

```python
disk.read_head()                 # "a" or "b"
disk.read_slot("a" | "b")       # durable/volatile bytes, or None
disk.write_slot("a" | "b", data: bytes)
disk.flush_slot("a" | "b")
disk.publish("a" | "b")
```

There are exactly two slots.  `write_slot` changes volatile memory only.
`flush_slot` normally makes the entire volatile value durable.  If power is
lost during it, however, the durable slot can contain any tested prefix of the
new bytes followed by the corresponding suffix of the old bytes (and can
therefore be corrupt).  `publish` atomically changes the durable head: after a
crash, the old or new head is observed.  Power loss discards all volatile data
and Python memory.  The verifier restarts by constructing a fresh disk image
and calling `recover`.

The supplied initial image and every state you publish use this slot format:

```python
encode_state(state) -> bytes
decode_state(data) -> state       # raises InvalidRecord on corruption
```

Both helpers are exported by `durable.py`.  A slot is at most 65,536 bytes.
Do not access attributes whose names begin with `_`, inspect stack frames, or
use filesystem/network/process APIs.  The verifier may reject such access.

## Required crash semantics

- After `apply` returns, the transaction is durable.
- At every possible power loss before return, a subsequent `recover` must yield
  exactly the complete pre-transaction state or complete post-transaction
  state—never corruption or a partial transfer.
- Retrying the same `(txid, changes)` after any crash must eventually produce
  the post-state exactly once.  Repeating it after success is a zero-write
  no-op.
- `recover` is deterministic, performs no disk mutations, and is idempotent.
- A successful new transaction uses at most eight mutating device calls.

All correctness rules, crash points, encodings, and resource limits used for
grading are stated above.  Hidden cases vary account names, balances,
transaction shapes, prior transaction history, slot/head position, and torn
flush positions.

