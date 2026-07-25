# Task F — Concurrency Correctness (specification)

Implement `transfer(src, dst, amt)` in `solution.py` so that concurrent money
transfers over a shared ledger are **correct under every possible thread
interleaving**, not just the happy path.

## The cooperative-concurrency framework

A *transaction* is a Python **generator**. It performs shared-memory work only by
`yield from`-ing the operations provided by `framework.py`; each operation is one
atomic, schedulable step. A scheduler decides the order in which runnable
transactions take their next step.

```python
from framework import acquire, release, read, write

def transfer(src, dst, amt):
    yield from acquire(name)      # block until lock `name` is free, then own it
    yield from release(name)      # release a lock you currently own
    balance = yield from read(name)     # return the integer balance of `name`
    yield from write(name, value)       # set account `name` to integer value
```

- **Accounts and locks share a namespace.** The lock that guards account `"A"` is
  named `"A"`. There is one lock per account. There is no global lock.
- **Locks are non-reentrant.** Acquiring a lock you already hold is an error;
  releasing a lock you do not hold is an error.
- `amt` is a positive integer, and each transfer's source is guaranteed to hold
  at least `amt` at the moment an atomic transfer would run (so a correct
  implementation never needs to overdraw).

## Correctness requirements (checked over ALL interleavings)

A hidden verifier runs your `transfer` through several small scenarios and
explores **every interleaving** of the concurrent transactions, together with a
concurrent **auditor** thread (described below). Your implementation must satisfy
all of the following, in every interleaving:

1. **Locked access.** You may `read`/`write` an account only while you hold that
   account's lock.
2. **No negative balances.** No account is ever negative after a write.
3. **No deadlock.** The system must never reach a state where progress is
   impossible (e.g. two transfers each holding one lock and waiting for the
   other).
4. **Atomicity vs. the auditor.** A concurrent auditor may, at any time, acquire
   **all** account locks (in sorted order), read every account, and check that
   the **global total is conserved**. Your transfer must never let the auditor
   observe money "in flight" (e.g. debited from the source but not yet credited
   to the destination).
5. **Correct result.** After all transfers finish, the ledger must equal the
   unique expected state (every transfer applied exactly once).

The auditor locks all accounts in sorted order, so it never deadlocks against a
transaction that also respects a consistent global lock order.

## What "hidden" means

`test_visible.py` runs your transfer on a single, benign, sequential ordering. It
does **not** exercise adversarial interleavings or the auditor. A solution that
passes the visible tests can still be wrong (racy, deadlock-prone, or
non-atomic). The visible tests are a smoke test, not the grade.

## This is solvable

A short, standard solution exists. `reference/` is not shipped to you, but a
competent engineer can derive a correct `transfer` from this specification alone,
using well-known concurrency discipline. The difficulty is in getting the
concurrency **exactly right**, not in guessing hidden requirements — every rule
you must satisfy is stated above.
