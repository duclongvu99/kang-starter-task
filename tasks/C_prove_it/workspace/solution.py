"""Candidate solution for the constrained-assignment task.

Implement `solve` exactly per SPEC.md. See README.md for the rules.
"""
from __future__ import annotations


def solve(instance: dict) -> dict:
    """Return either:

        {"status": "optimal", "assignment": {job_id: machine_id, ...}}

    for a FEASIBLE instance (the assignment must be valid AND cost-optimal —
    see SPEC.md sections 3-4), or:

        {"status": "infeasible", "certificate": [job_id, ...]}

    for an INFEASIBLE instance (the certificate must be a minimal infeasible
    subset of jobs — see SPEC.md section 4).
    """
    raise NotImplementedError("implement solve() per SPEC.md")
