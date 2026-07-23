"""Visible test suite for the constrained-assignment task.

Run with:  python -m pytest test_visible.py -q

NOTE: these are a handful of small, easy example instances provided for
convenience/sanity-checking only. They are NOT the grading battery — see
README.md and SPEC.md section 5. Passing every test here is neither
necessary nor sufficient for a correct solution.
"""
from solution import solve


def _cost_of(instance, assignment):
    return sum(instance["cost"][j][m] for j, m in assignment.items())


def _is_valid(instance, assignment):
    jobs, allowed = instance["jobs"], instance["allowed"]
    capacity, conflicts = instance["capacity"], instance.get("conflicts", [])
    if set(assignment.keys()) != set(jobs):
        return False
    for j, m in assignment.items():
        if m not in allowed.get(j, []):
            return False
    used = {}
    for m in assignment.values():
        used[m] = used.get(m, 0) + 1
    for m, n in used.items():
        if n > capacity.get(m, 0):
            return False
    for j1, j2 in conflicts:
        if j1 in assignment and j2 in assignment and assignment[j1] == assignment[j2]:
            return False
    return True


def test_single_job_single_machine():
    instance = {
        "jobs": ["j0"],
        "machines": ["m0"],
        "allowed": {"j0": ["m0"]},
        "capacity": {"m0": 1},
        "conflicts": [],
        "cost": {"j0": {"m0": 7}},
    }
    result = solve(instance)
    assert result["status"] == "optimal"
    assert result["assignment"] == {"j0": "m0"}


def test_two_jobs_two_machines_no_contention():
    # Ample capacity, disjoint cheap choices -> greedy-per-job is optimal.
    instance = {
        "jobs": ["j0", "j1"],
        "machines": ["m0", "m1"],
        "allowed": {"j0": ["m0", "m1"], "j1": ["m0", "m1"]},
        "capacity": {"m0": 2, "m1": 2},
        "conflicts": [],
        "cost": {"j0": {"m0": 1, "m1": 9}, "j1": {"m0": 9, "m1": 1}},
    }
    result = solve(instance)
    assert result["status"] == "optimal"
    assert _is_valid(instance, result["assignment"])
    assert _cost_of(instance, result["assignment"]) == 2


def test_three_jobs_three_machines_ample_capacity():
    instance = {
        "jobs": ["j0", "j1", "j2"],
        "machines": ["m0", "m1", "m2"],
        "allowed": {
            "j0": ["m0", "m1", "m2"],
            "j1": ["m0", "m1", "m2"],
            "j2": ["m0", "m1", "m2"],
        },
        "capacity": {"m0": 3, "m1": 3, "m2": 3},
        "conflicts": [],
        "cost": {
            "j0": {"m0": 2, "m1": 5, "m2": 8},
            "j1": {"m0": 6, "m1": 1, "m2": 9},
            "j2": {"m0": 7, "m1": 8, "m2": 3},
        },
    }
    result = solve(instance)
    assert result["status"] == "optimal"
    assert _is_valid(instance, result["assignment"])
    assert _cost_of(instance, result["assignment"]) == 2 + 1 + 3


def test_restricted_allowed_sets_still_feasible():
    instance = {
        "jobs": ["j0", "j1", "j2"],
        "machines": ["m0", "m1"],
        "allowed": {"j0": ["m0"], "j1": ["m0", "m1"], "j2": ["m1"]},
        "capacity": {"m0": 2, "m1": 2},
        "conflicts": [],
        "cost": {"j0": {"m0": 4}, "j1": {"m0": 1, "m1": 2}, "j2": {"m1": 5}},
    }
    result = solve(instance)
    assert result["status"] == "optimal"
    assert _is_valid(instance, result["assignment"])
    assert _cost_of(instance, result["assignment"]) == 4 + 1 + 5


def test_harmless_conflict_does_not_bind():
    # A conflict exists, but ample capacity elsewhere means the cheapest
    # per-job choice never actually puts the conflicting pair together.
    instance = {
        "jobs": ["j0", "j1", "j2", "j3"],
        "machines": ["m0", "m1", "m2"],
        "allowed": {
            "j0": ["m0", "m1"],
            "j1": ["m1", "m2"],
            "j2": ["m0", "m1", "m2"],
            "j3": ["m0", "m1", "m2"],
        },
        "capacity": {"m0": 2, "m1": 4, "m2": 2},
        "conflicts": [["j0", "j1"]],
        "cost": {
            "j0": {"m0": 1, "m1": 5},
            "j1": {"m1": 5, "m2": 1},
            "j2": {"m0": 3, "m1": 2, "m2": 3},
            "j3": {"m0": 3, "m1": 2, "m2": 3},
        },
    }
    result = solve(instance)
    assert result["status"] == "optimal"
    assert _is_valid(instance, result["assignment"])
    assert _cost_of(instance, result["assignment"]) == 1 + 1 + 2 + 2
