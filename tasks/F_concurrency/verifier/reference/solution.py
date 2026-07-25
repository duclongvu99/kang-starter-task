"""Reference solution: two-phase locking with a GLOBAL lock order.

Correct under every interleaving: acquiring both locks in a canonical (sorted)
order makes deadlock impossible, and holding BOTH locks across the whole
read-modify-write of both accounts makes the transfer atomic w.r.t. any auditor.
"""
from framework import acquire, release, read, write


def transfer(src, dst, amt):
    first, second = sorted([src, dst])          # global order -> no deadlock
    yield from acquire(first)
    yield from acquire(second)
    src_bal = yield from read(src)               # atomic: both locks held throughout
    yield from write(src, src_bal - amt)
    dst_bal = yield from read(dst)
    yield from write(dst, dst_bal + amt)
    yield from release(second)
    yield from release(first)
