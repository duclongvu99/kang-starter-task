"""Known-bad: locks every access correctly and uses a consistent order, but
releases the source lock before crediting the destination. A concurrent auditor
can then observe money "in flight" (debited but not yet credited) -> the total
looks non-conserved. Passes the happy path and even looks well-synchronized."""
from framework import acquire, release, read, write


def transfer(src, dst, amt):
    yield from acquire(src)
    src_bal = yield from read(src)
    yield from write(src, src_bal - amt)
    yield from release(src)                      # released too early: not atomic
    yield from acquire(dst)
    dst_bal = yield from read(dst)
    yield from write(dst, dst_bal + amt)
    yield from release(dst)
