"""Known-bad: holds both locks (atomic) but acquires them in CALL order, not a
global order. Two transfers in opposite directions deadlock. Passes happy path."""
from framework import acquire, release, read, write


def transfer(src, dst, amt):
    yield from acquire(src)                      # no global order -> deadlock
    yield from acquire(dst)
    src_bal = yield from read(src)
    yield from write(src, src_bal - amt)
    dst_bal = yield from read(dst)
    yield from write(dst, dst_bal + amt)
    yield from release(dst)
    yield from release(src)
