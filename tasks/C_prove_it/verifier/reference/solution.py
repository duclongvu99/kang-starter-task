"""Reference solution for Task C (correct, z3-based). Used only by the
grader-validity gate (--self-test); never shown to candidate agents.

Independently implemented from oracle.py (same underlying method - an exact
z3 formulation of SPEC.md sections 3-4 - since the spec is unambiguous both
converge on the same answers; that convergence is itself part of what the
grader-validity gate checks)."""
from __future__ import annotations

import z3


def _vars_and_constraints(solver, jobs, machines, allowed, capacity, conflicts):
    x = {}
    for j in jobs:
        for m in allowed.get(j, []):
            x[(j, m)] = z3.Bool(f"x__{j}__{m}")
    for j in jobs:
        opts = [x[(j, m)] for m in allowed.get(j, [])]
        if not opts:
            solver.add(z3.BoolVal(False))
            continue
        solver.add(z3.PbEq([(v, 1) for v in opts], 1))
    for m in machines:
        users = [x[(j, m)] for j in jobs if (j, m) in x]
        if users:
            solver.add(z3.PbLe([(v, 1) for v in users], int(capacity.get(m, 0))))
    jobset = set(jobs)
    for pair in conflicts:
        j1, j2 = pair[0], pair[1]
        if j1 not in jobset or j2 not in jobset:
            continue
        for m in machines:
            if (j1, m) in x and (j2, m) in x:
                solver.add(z3.Not(z3.And(x[(j1, m)], x[(j2, m)])))
    return x


def _is_feasible(instance, jobs):
    if not jobs:
        return True
    s = z3.Solver()
    _vars_and_constraints(s, jobs, instance["machines"], instance["allowed"],
                          instance["capacity"], instance.get("conflicts", []))
    return s.check() == z3.sat


def _minimal_infeasible_subset(instance):
    jobs = list(instance["jobs"])
    S = list(jobs)
    for j in jobs:
        if j not in S:
            continue
        T = [x for x in S if x != j]
        if not _is_feasible(instance, T):
            S = T
    return S


def solve(instance: dict) -> dict:
    jobs = instance["jobs"]
    if not _is_feasible(instance, jobs):
        return {"status": "infeasible", "certificate": _minimal_infeasible_subset(instance)}

    allowed = instance["allowed"]
    cost = instance["cost"]
    opt = z3.Optimize()
    x = _vars_and_constraints(opt, jobs, instance["machines"], allowed,
                              instance["capacity"], instance.get("conflicts", []))
    terms = []
    for j in jobs:
        for m in allowed.get(j, []):
            terms.append(z3.If(x[(j, m)], int(cost[j][m]), 0))
    opt.minimize(z3.Sum(terms) if terms else z3.IntVal(0))
    res = opt.check()
    assert res == z3.sat
    model = opt.model()
    assignment = {}
    for j in jobs:
        for m in allowed.get(j, []):
            if z3.is_true(model.eval(x[(j, m)], model_completion=True)):
                assignment[j] = m
                break
    return {"status": "optimal", "assignment": assignment}
