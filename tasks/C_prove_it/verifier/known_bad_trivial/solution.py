"""Trivial do-nothing baseline for Task C's grader-validity gate. Must FAIL:
it never attempts any real work, and an empty certificate is never a valid
minimal-infeasible-subset (the empty sub-instance is always vacuously
feasible), so this fails even on genuinely infeasible instances."""
from __future__ import annotations


def solve(instance: dict) -> dict:
    return {"status": "infeasible", "certificate": []}
