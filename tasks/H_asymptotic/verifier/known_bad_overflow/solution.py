"""Known-bad: asymptotically efficient (O(N log N)) but accumulates in 64-bit
arithmetic. Correct on small instances, WRONG at scale because the true sum
exceeds 2**63 and wraps. This is the fast-but-careless failure — the kind an
agent that reaches for numpy int64 or a C accumulator would produce."""

_MASK = (1 << 64) - 1


def _wrap(x):
    # Simulate unsigned 64-bit wraparound (what a uint64 accumulator would do).
    return x & _MASK


def solve(a):
    b = sorted(a)
    total = 0
    prefix = 0
    for k, v in enumerate(b):
        total = _wrap(total + _wrap(v * k) - prefix)
        prefix = _wrap(prefix + v)
    return total
