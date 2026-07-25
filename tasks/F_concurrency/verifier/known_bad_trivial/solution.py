"""Trivial baseline: does nothing. Must FAIL (wrong final state) -- the
grader-validity gate's non-discrimination check (G8)."""


def transfer(src, dst, amt):
    return
    yield  # makes this a generator function
