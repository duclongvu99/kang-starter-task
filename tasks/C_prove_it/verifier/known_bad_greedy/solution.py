"""Known-BAD submission for Task C's grader-validity gate.

Models a very plausible naive-agent mistake: a pure greedy assignment with
NO backtracking and NO awareness of the conflict constraint at all. For
each job (in the given order) it picks the cheapest allowed machine that
still has spare capacity; it never checks rule 3 (conflicts) from SPEC.md
at all.

This is optimal on small, slack instances with no capacity contention and
no binding conflicts (which is exactly what the visible tests look like),
but on the hidden adversarial battery it:
  - locks in an early cheap choice that turns out to be globally suboptimal
    once capacity runs out for later jobs (suboptimal_cost), or
  - happily assigns two conflicting jobs to the same machine, producing an
    assignment that LOOKS "optimal" but is not even valid
    (infeasible_assignment_returned / missed_infeasibility when that is the
    only thing making the instance infeasible), or
  - when it can't place every job due to capacity, reports the leftover
    "unassigned" jobs as an infeasibility "certificate", which is generally
    neither infeasible-by-itself nor minimal (wrong_certificate).
"""
from __future__ import annotations


def solve(instance: dict) -> dict:
    jobs = instance["jobs"]
    allowed = instance["allowed"]
    capacity = instance["capacity"]
    cost = instance["cost"]

    remaining = dict(capacity)
    assignment = {}
    unassigned = []

    for j in jobs:
        candidates = sorted(allowed.get(j, []), key=lambda m: cost.get(j, {}).get(m, float("inf")))
        placed = False
        for m in candidates:
            if remaining.get(m, 0) > 0:
                assignment[j] = m
                remaining[m] -= 1
                placed = True
                break
        if not placed:
            unassigned.append(j)

    if unassigned:
        return {"status": "infeasible", "certificate": unassigned}
    return {"status": "optimal", "assignment": assignment}
