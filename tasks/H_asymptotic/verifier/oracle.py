"""Trusted oracle for Task H — sum of pairwise absolute differences.

`pair_abs_sum` is the O(N log N) ground truth. It is validated against the
O(N^2) brute force on small random instances in verify.py --self-test (gate
G3a: the oracle is certified on known ground truth before it decides anything).
Both use Python's arbitrary-precision ints, so neither ever overflows.
"""
from __future__ import annotations

import random

VALUE_MAX = 10**9


def make_array(n: int, seed: int) -> list[int]:
    """Deterministic instance: the same (n, seed) always yields the same array."""
    rng = random.Random(seed)
    return [rng.randint(0, VALUE_MAX) for _ in range(n)]


def pair_abs_sum(a: list[int]) -> int:
    """Sum over all pairs i<j of |a[i]-a[j]|, in O(N log N).

    Sort ascending; for the sorted array b, |b[i]-b[j]| = b[j]-b[i] for i<j, so
    element b[k] (0-indexed rank k) contributes b[k]*k - (b[0]+...+b[k-1]).
    """
    b = sorted(a)
    total = 0
    prefix = 0
    for k, v in enumerate(b):
        total += v * k - prefix
        prefix += v
    return total


def pair_abs_sum_bruteforce(a: list[int]) -> int:
    """O(N^2) reference, used only to certify pair_abs_sum on small instances."""
    n = len(a)
    total = 0
    for i in range(n):
        ai = a[i]
        for j in range(i + 1, n):
            d = ai - a[j]
            total += d if d >= 0 else -d
    return total
