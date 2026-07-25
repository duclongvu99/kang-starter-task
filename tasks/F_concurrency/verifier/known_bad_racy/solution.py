"""Known-bad: no locking at all. Reads/writes accounts without holding their
locks, so concurrent transfers lose updates. Passes happy path (no contention)."""
from framework import read, write


def transfer(src, dst, amt):
    src_bal = yield from read(src)               # unlocked access -> lost updates
    yield from write(src, src_bal - amt)
    dst_bal = yield from read(dst)
    yield from write(dst, dst_bal + amt)
