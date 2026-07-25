"""Hidden verifier core: exhaustive interleaving model checker + concurrent auditor.

This is NOT shipped into the candidate's workspace. It explores EVERY interleaving
of a small scenario by replay (stateless model checking, Verisoft-style): a
schedule is a sequence of thread choices; to evaluate a prefix we re-run from the
initial state with fresh generators and step threads in the chosen order. Because
the state is tiny and bounded, the whole reachable interleaving space is covered,
so "no violation found" is a proof over all interleavings (up to the state cap),
not a sample. No LLM judge is involved -- verdicts come from executing the
candidate's own code under an adversarial-but-real scheduler.

Checked properties (a correct transaction must satisfy ALL, under EVERY interleaving):
  - locked access : a read/write of account X requires owning lock X
  - safety        : no account is ever negative after a write
  - progress      : no reachable deadlock (some thread blocked forever)
  - atomicity     : a concurrent auditor that locks all accounts and reads them
                    must never observe a non-conserved total (money in flight)
  - correctness   : every terminated interleaving ends in the expected state
"""
from __future__ import annotations

from framework import acquire, release


class VerifierCapExceeded(Exception):
    """Raised if the interleaving search exceeds its state cap (scenario too big)."""


class DoubleAcquire(Exception):
    pass


class BadRelease(Exception):
    pass


def auditor(names, total):
    """Verifier-controlled thread: atomically snapshots the whole ledger and
    asserts the global total is conserved. It locks every account (in canonical
    sorted order, so it never introduces a deadlock against a correctly-ordered
    transaction), reads the total, then releases."""
    for name in names:
        yield from acquire(name)
    yield ("assert_total", total)
    for name in reversed(names):
        yield from release(name)


def _prime(gen):
    try:
        return next(gen)
    except StopIteration:
        return None


def _blocked(op, owner, tid):
    return op is not None and op[0] == "acquire" and owner[op[1]] not in (None, tid)


def check_scenario(make_threads, accounts0, expected, *, cap=3_000_000):
    """Return (violations, nodes). `make_threads` is a 0-arg factory returning a
    FRESH list of thread generators each call (required for replay). `violations`
    is empty iff the implementation is correct on every explored interleaving."""
    violations: list[dict] = []
    nodes = 0

    def run_prefix(choices):
        accounts = dict(accounts0)
        owner = {a: None for a in accounts}
        gens = make_threads()
        nextops = [_prime(g) for g in gens]
        done = [op is None for op in nextops]
        neg = None
        unlocked = None
        audit = None
        for c in choices:
            op = nextops[c]
            kind = op[0]
            send = None
            if kind == "acquire":
                name = op[1]
                if owner[name] == c:
                    raise DoubleAcquire(f"thread {c} re-acquires {name}")
                owner[name] = c
            elif kind == "release":
                name = op[1]
                if owner[name] != c:
                    raise BadRelease(f"thread {c} releases {name} it does not own")
                owner[name] = None
            elif kind == "read":
                name = op[1]
                if owner[name] != c and unlocked is None:
                    unlocked = ("read", name)
                send = accounts[name]
            elif kind == "write":
                name = op[1]
                if owner[name] != c and unlocked is None:
                    unlocked = ("write", name)
                accounts[name] = op[2]
                if op[2] < 0 and neg is None:
                    neg = name
            elif kind == "assert_total":
                if sum(accounts.values()) != op[1] and audit is None:
                    audit = {"saw": sum(accounts.values()), "expected": op[1]}
            try:
                nextops[c] = gens[c].send(send)
            except StopIteration:
                nextops[c] = None
                done[c] = True
            if unlocked is not None or audit is not None:
                break
        return accounts, owner, nextops, done, neg, unlocked, audit

    def dfs(choices):
        nonlocal nodes
        nodes += 1
        if nodes > cap:
            raise VerifierCapExceeded(f"exceeded {cap} states")
        accounts, owner, nextops, done, neg, unlocked, audit = run_prefix(choices)
        n = len(done)
        if unlocked is not None:
            violations.append({"type": "unlocked_access", "op": unlocked[0],
                               "account": unlocked[1], "schedule": list(choices)})
            return
        if audit is not None:
            violations.append({"type": "audit_saw_inconsistent_total", **audit,
                               "schedule": list(choices)})
            return
        if neg is not None:
            violations.append({"type": "negative_balance", "account": neg,
                               "schedule": list(choices)})
            return
        runnable = [i for i in range(n) if not done[i] and not _blocked(nextops[i], owner, i)]
        if not runnable:
            if all(done):
                if accounts != expected:
                    violations.append({"type": "wrong_final_state", "got": dict(accounts),
                                       "expected": dict(expected), "schedule": list(choices)})
            else:
                blocked_on = {i: nextops[i][1] for i in range(n) if not done[i]}
                violations.append({"type": "deadlock", "blocked": blocked_on,
                                   "schedule": list(choices)})
            return
        for i in runnable:
            dfs(choices + [i])
            if len(violations) >= 50:
                return

    dfs([])
    return violations, nodes
