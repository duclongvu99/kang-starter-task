"""Independent, authoritative z3-based solver for Task C.

This is the ground-truth arbiter used by verify.py to grade candidate
submissions. It is written independently of any candidate solution, using
z3's pseudo-boolean constraints directly against the formal model in
SPEC.md sections 3-4. It is validated (in verify.py's --self-test gate)
against hand-computed instances AND against an independent brute-force
search on small random instances before it is trusted.
"""
from __future__ import annotations

import itertools

import z3


def _vars_and_constraints(solver, jobs, machines, allowed, capacity, conflicts):
    """Build x[j,m] Bool vars for j in jobs, m in allowed[j], add constraints
    1-3 from SPEC.md section 3 to `solver`. Returns the var dict."""
    x = {}
    for j in jobs:
        for m in allowed.get(j, []):
            x[(j, m)] = z3.Bool(f"x__{j}__{m}")

    # Rule 1: exactly one machine per job (an empty allowed[j] is UNSAT).
    for j in jobs:
        opts = [x[(j, m)] for m in allowed.get(j, [])]
        if not opts:
            solver.add(z3.BoolVal(False))
            continue
        solver.add(z3.PbEq([(v, 1) for v in opts], 1))

    # Rule 2: capacity per machine.
    for m in machines:
        users = [x[(j, m)] for j in jobs if (j, m) in x]
        if users:
            solver.add(z3.PbLe([(v, 1) for v in users], int(capacity.get(m, 0))))

    # Rule 3: conflicting jobs never share a machine.
    jobset = set(jobs)
    for pair in conflicts:
        j1, j2 = pair[0], pair[1]
        if j1 not in jobset or j2 not in jobset:
            continue
        for m in machines:
            if (j1, m) in x and (j2, m) in x:
                solver.add(z3.Not(z3.And(x[(j1, m)], x[(j2, m)])))
    return x


def is_feasible(instance, jobs=None):
    """True iff the instance (or the sub-instance restricted to `jobs`, if
    given) has a valid assignment satisfying SPEC.md rules 1-3."""
    jobs = instance["jobs"] if jobs is None else list(jobs)
    if not jobs:
        return True  # vacuously feasible: no jobs to place
    s = z3.Solver()
    _vars_and_constraints(s, jobs, instance["machines"], instance["allowed"],
                          instance["capacity"], instance.get("conflicts", []))
    return s.check() == z3.sat


def true_optimum(instance):
    """Assumes the instance is feasible. Returns (min_cost, assignment)."""
    jobs = instance["jobs"]
    allowed = instance["allowed"]
    cost = instance["cost"]
    opt = z3.Optimize()
    x = _vars_and_constraints(opt, jobs, instance["machines"], allowed,
                              instance["capacity"], instance.get("conflicts", []))
    terms = []
    for j in jobs:
        for m in allowed.get(j, []):
            c = int(cost[j][m])
            terms.append(z3.If(x[(j, m)], c, 0))
    total = z3.Sum(terms) if terms else z3.IntVal(0)
    opt.minimize(total)
    res = opt.check()
    assert res == z3.sat, "true_optimum() called on an infeasible instance"
    model = opt.model()
    assignment = {}
    for j in jobs:
        for m in allowed.get(j, []):
            if z3.is_true(model.eval(x[(j, m)], model_completion=True)):
                assignment[j] = m
                break
    achieved = sum(cost[j][assignment[j]] for j in jobs)
    return achieved, assignment


def minimal_infeasible_subset(instance):
    """Assumes the full instance (all of instance['jobs']) is infeasible.
    Returns a minimal infeasible subset of job ids via deletion filtering:
    repeatedly try dropping each job; keep the drop permanently if the
    smaller set is still infeasible. This is the standard deletion-based
    MUS-extraction algorithm; it is correct here because infeasibility is
    monotone under adding jobs (removing jobs can only relax constraints 1-3,
    never tighten them), which is what makes "drop while still UNSAT" sound
    and the final set provably minimal (see verifier notes / SPEC.md)."""
    jobs = list(instance["jobs"])
    S = list(jobs)
    for j in jobs:
        if j not in S:
            continue
        T = [x for x in S if x != j]
        if not is_feasible(instance, T):
            S = T
    return S


def brute_force(instance):
    """Exhaustive (non-z3) ground truth for SMALL instances only, used
    purely to validate the z3 formulation above against an independent
    method. Returns (feasible: bool, min_cost_or_None).

    Tries every combination of allowed machines per job (cartesian product)
    and checks validity directly against SPEC.md rules 1-3. Exponential —
    only safe for a handful of jobs."""
    jobs = instance["jobs"]
    allowed = instance["allowed"]
    capacity = instance["capacity"]
    conflicts = [tuple(p) for p in instance.get("conflicts", [])]
    cost = instance["cost"]

    if any(not allowed.get(j) for j in jobs):
        return False, None

    best = None
    for combo in itertools.product(*(allowed[j] for j in jobs)):
        assignment = dict(zip(jobs, combo))
        used = {}
        for m in combo:
            used[m] = used.get(m, 0) + 1
        if any(n > capacity.get(m, 0) for m, n in used.items()):
            continue
        if any(assignment.get(j1) == assignment.get(j2) for j1, j2 in conflicts):
            continue
        c = sum(cost[j][assignment[j]] for j in jobs)
        if best is None or c < best:
            best = c
    return (best is not None), best
