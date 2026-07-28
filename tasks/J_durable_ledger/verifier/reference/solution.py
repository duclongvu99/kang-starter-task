from __future__ import annotations

import hashlib
import re

from durable import canonical_json, decode_state, encode_state


class TransactionRejected(ValueError):
    pass


class TransactionConflict(ValueError):
    pass


def recover(disk):
    data = disk.read_slot(disk.read_head())
    if data is None:
        raise ValueError("published slot is empty")
    state = decode_state(data)
    return {
        "accounts": dict(state["accounts"]),
        "applied": dict(state["applied"]),
    }


def _fingerprint(changes):
    return hashlib.sha256(canonical_json(changes).encode("utf-8")).hexdigest()


def apply(disk, txid, changes):
    state = recover(disk)
    if not isinstance(txid, str) or re.fullmatch(r"[A-Za-z0-9._-]{1,64}", txid) is None:
        raise TransactionRejected("invalid transaction id")
    if type(changes) is not dict or not changes:
        raise TransactionRejected("changes must be a non-empty plain dict")
    if any(
        not isinstance(name, str)
        or name not in state["accounts"]
        or type(delta) is not int
        or delta == 0
        for name, delta in changes.items()
    ):
        raise TransactionRejected("invalid change")
    if sum(changes.values()) != 0:
        raise TransactionRejected("deltas do not balance")
    fingerprint = _fingerprint(changes)
    previous = state["applied"].get(txid)
    if previous is not None:
        if previous != fingerprint:
            raise TransactionConflict("transaction id reused")
        return

    updated = dict(state["accounts"])
    for name, delta in changes.items():
        updated[name] += delta
    if any(balance < 0 for balance in updated.values()):
        raise TransactionRejected("negative balance")

    post = {"accounts": updated, "applied": dict(state["applied"])}
    post["applied"][txid] = fingerprint
    old = disk.read_head()
    target = "b" if old == "a" else "a"
    disk.write_slot(target, encode_state(post))
    disk.flush_slot(target)
    disk.publish(target)
