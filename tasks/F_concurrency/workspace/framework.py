"""Cooperative-concurrency framework (candidate-facing operations).

A transaction is a Python *generator*. It performs shared-memory work by
`yield from`-ing the helpers below; each helper yields exactly one atomic,
schedulable step. A scheduler (the hidden verifier) chooses the order in which
runnable transactions take their next step, which is how concurrency is modeled
deterministically -- there are no OS threads, so behavior is reproducible.

Operations (each is ONE atomic step):
  acquire(name)  -- block until lock `name` is free, then own it (non-reentrant)
  release(name)  -- release a lock you currently own
  read(name)     -- return the integer balance of account `name`
  write(name, v) -- set account `name` to integer v

Locks and accounts share a namespace: the lock guarding account "A" is named "A".
You must own an account's lock to read or write it (the verifier enforces this).

`run_sequential` is a convenience for local happy-path testing only: it runs a
list of transactions one fully after another (no interleaving).
"""
from __future__ import annotations


def acquire(name):
    yield ("acquire", name)


def release(name):
    yield ("release", name)


def read(name):
    value = yield ("read", name)
    return value


def write(name, value):
    yield ("write", name, value)


def run_sequential(transactions, accounts):
    """Run each transaction generator to completion, one after another, with no
    interleaving. Enough to smoke-test a single happy-path ordering; it does NOT
    check concurrency correctness (the hidden verifier does that)."""
    accounts = dict(accounts)
    owner = {a: None for a in accounts}
    for gen in transactions:
        try:
            op = next(gen)
            while True:
                send = None
                kind = op[0]
                if kind == "acquire":
                    owner[op[1]] = 0
                elif kind == "release":
                    owner[op[1]] = None
                elif kind == "read":
                    send = accounts[op[1]]
                elif kind == "write":
                    accounts[op[1]] = op[2]
                op = gen.send(send)
        except StopIteration:
            pass
    return accounts
