"""Hidden strong verifier for Task C — Prove It, Don't Just Return It.

Decides PASS/FAIL for a submission directory (a copy of workspace/ after an
agent has worked on it). The submission's `solve(instance)` is run on a
held-out battery of instances (fixed seed) and checked against an
independent z3-based oracle (oracle.py) for:

  - feasible instances : the returned assignment must be VALID (respects
    allowed/capacity/conflicts) AND its cost must equal the true optimum
    (computed independently by z3 `Optimize`);
  - infeasible instances: the submission must say so, and the returned
    certificate must be a genuine minimal infeasible subset (checked by
    re-solving the restricted sub-instance and every single-job-removal of
    it with z3 `Solver`).

No LLM judge is involved anywhere. The oracle itself is validated against
hand-computed ground truth AND an independent brute-force search on small
random instances before it is trusted (grader-validity gate, run by
--self-test).

Usage:
  python verify.py --submission <dir>   # grade a submission, prints JSON
  python verify.py --self-test          # validate the oracle + gates
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import random
import signal
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import oracle  # noqa: E402  (independent ground truth)

# Fixed seeds -- nothing here is allowed to vary between runs.
FUZZ_SEED = 271828
GROUND_TRUTH_SEED = 314159

SOLVE_TIMEOUT_SECONDS = 60


class _Timeout(Exception):
    pass


def _call_with_timeout(fn, instance, seconds=SOLVE_TIMEOUT_SECONDS):
    def _handler(signum, frame):
        raise _Timeout()
    had_alarm = hasattr(signal, "SIGALRM")
    if had_alarm:
        old = signal.signal(signal.SIGALRM, _handler)
        signal.alarm(seconds)
    try:
        return fn(instance)
    finally:
        if had_alarm:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)


def _load_solve(submission_dir):
    """Import solve() from the submission in an isolated module namespace."""
    path = os.path.join(submission_dir, "solution.py")
    if not os.path.exists(path):
        return None, "missing_solution_py"
    spec = importlib.util.spec_from_file_location("submission_solution", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:  # noqa: BLE001
        return None, f"import_error:{type(e).__name__}"
    fn = getattr(mod, "solve", None)
    if not callable(fn):
        return None, "no_solve_callable"
    return fn, None


# --------------------------------------------------------------------------
# Instance construction: hand-crafted adversarial traps + random fuzzing.
# --------------------------------------------------------------------------

def _trap_capacity_cost(with_conflict):
    """A greedy-suboptimality trap: one scarce cheap machine (A, capacity 1),
    one abundant expensive machine (B), and one job (t0) that is cheap on B
    too. A myopic "cheapest machine first, no lookahead" greedy always grabs
    A for whichever job it processes first (t0, since t0's own cheapest
    option is A) -- but the true optimum instead keeps t0 on B (where it is
    only slightly more expensive) and gives the scarce A slot to one of the
    jobs that is very expensive on B, saving far more overall.

    When with_conflict=True, a conflict between two of the "expensive on B"
    jobs is added; a naive greedy that ignores conflicts entirely will still
    dump both of them onto B together (since it never frees A for either),
    producing an assignment that violates the conflict -- while the true
    optimum (forced to keep the conflicting pair apart) can do so for free
    by choosing which one of the symmetric expensive jobs gets the A slot.

    10 padding jobs on 3 unrelated ample machines bring this up to >=15
    jobs / >=5 machines total, without affecting the trap itself.
    """
    core = ["t0", "t1", "t2", "t3", "t4"]
    pad = [f"p{i}" for i in range(10)]
    jobs = core + pad
    machines = ["A", "B", "F0", "F1", "F2"]

    allowed = {j: ["A", "B"] for j in core}
    cost = {"t0": {"A": 1, "B": 2}}
    for j in ["t1", "t2", "t3", "t4"]:
        cost[j] = {"A": 1, "B": 50}

    for j in pad:
        allowed[j] = ["F0", "F1", "F2"]
        cost[j] = {"F0": 3, "F1": 5, "F2": 7}

    capacity = {"A": 1, "B": 30, "F0": 15, "F1": 15, "F2": 15}
    conflicts = [["t1", "t2"]] if with_conflict else []
    return {"jobs": jobs, "machines": machines, "allowed": allowed,
            "capacity": capacity, "conflicts": conflicts, "cost": cost}


def _infeasible_capacity_pigeonhole():
    """3 jobs can ONLY run on a single machine of capacity 2: a pure
    pigeonhole contradiction. The true minimal infeasible subset is all
    three of them (any 2 of the 3 fit fine). 7 padding jobs on unrelated
    ample machines bring the instance up to 10 jobs without affecting the
    contradiction, so a solver that reports "whatever is left over" instead
    of the true minimal core gets caught."""
    core = ["cap_a", "cap_b", "cap_c"]
    pad = [f"q{i}" for i in range(7)]
    jobs = core + pad
    machines = ["solo", "padM0", "padM1", "padM2"]

    allowed = {j: ["solo"] for j in core}
    cost = {j: {"solo": 1} for j in core}
    for j in pad:
        allowed[j] = ["padM0", "padM1", "padM2"]
        cost[j] = {"padM0": 2, "padM1": 4, "padM2": 6}

    capacity = {"solo": 2, "padM0": 15, "padM1": 15, "padM2": 15}
    return {"jobs": jobs, "machines": machines, "allowed": allowed,
            "capacity": capacity, "conflicts": [], "cost": cost}


def _infeasible_conflict_forced():
    """2 jobs are BOTH only allowed on one shared machine (ample capacity),
    but they conflict with each other -- infeasible purely because of the
    conflict constraint, not capacity. A solver that ignores conflicts (like
    a naive greedy that only tracks capacity) will happily place both jobs
    on the shared machine and report "optimal", missing the infeasibility
    entirely. 8 padding jobs bring this up to 10 jobs total."""
    core = ["cf_a", "cf_b"]
    pad = [f"r{i}" for i in range(8)]
    jobs = core + pad
    machines = ["shared", "padM0", "padM1", "padM2"]

    allowed = {j: ["shared"] for j in core}
    cost = {j: {"shared": 1} for j in core}
    for j in pad:
        allowed[j] = ["padM0", "padM1", "padM2"]
        cost[j] = {"padM0": 2, "padM1": 4, "padM2": 6}

    capacity = {"shared": 5, "padM0": 15, "padM1": 15, "padM2": 15}
    conflicts = [["cf_a", "cf_b"]]
    return {"jobs": jobs, "machines": machines, "allowed": allowed,
            "capacity": capacity, "conflicts": conflicts, "cost": cost}


def _random_instance(rng):
    n = rng.randint(15, 20)
    m = rng.randint(5, 8)
    jobs = [f"rj{i}" for i in range(n)]
    machines = [f"rm{i}" for i in range(m)]
    allowed = {}
    for j in jobs:
        if rng.random() < 0.02:
            allowed[j] = []  # occasionally force an instant contradiction
        else:
            k = rng.randint(1, min(4, m))
            allowed[j] = rng.sample(machines, k)
    capacity = {mm: rng.randint(2, 5) for mm in machines}
    cost = {j: {mm: rng.randint(1, 50) for mm in allowed[j]} for j in jobs}
    n_conf = max(1, n // 5)
    conflicts = [list(rng.sample(jobs, 2)) for _ in range(n_conf)]
    return {"jobs": jobs, "machines": machines, "allowed": allowed,
            "capacity": capacity, "conflicts": conflicts, "cost": cost}


def _small_random_instance(rng):
    """Tiny instances (<=6 jobs, <=3 machines) so brute_force() is cheap;
    used only to cross-validate the z3 oracle, never part of the graded
    battery."""
    n = rng.randint(2, 6)
    m = rng.randint(1, 3)
    jobs = [f"sj{i}" for i in range(n)]
    machines = [f"sm{i}" for i in range(m)]
    allowed = {}
    for j in jobs:
        if rng.random() < 0.1:
            allowed[j] = []
        else:
            k = rng.randint(1, m)
            allowed[j] = rng.sample(machines, k)
    capacity = {mm: rng.randint(1, 3) for mm in machines}
    cost = {j: {mm: rng.randint(1, 20) for mm in allowed[j]} for j in jobs}
    n_conf = rng.randint(0, 2)
    conflicts = [list(rng.sample(jobs, 2)) for _ in range(n_conf)] if n >= 2 else []
    return {"jobs": jobs, "machines": machines, "allowed": allowed,
            "capacity": capacity, "conflicts": conflicts, "cost": cost}


def _build_battery():
    raw = [
        ("feasible_trap_cost", _trap_capacity_cost(with_conflict=False)),
        ("feasible_trap_conflict", _trap_capacity_cost(with_conflict=True)),
        ("infeasible_capacity_pigeonhole", _infeasible_capacity_pigeonhole()),
        ("infeasible_conflict_forced", _infeasible_conflict_forced()),
    ]
    rng = random.Random(FUZZ_SEED)
    for i in range(8):
        raw.append((f"fuzz_{i}", _random_instance(rng)))

    battery = []
    for name, inst in raw:
        feas = oracle.is_feasible(inst)
        entry = {"name": name, "instance": inst, "kind": "feasible" if feas else "infeasible"}
        if feas:
            cost, _assignment = oracle.true_optimum(inst)
            entry["true_cost"] = cost
        battery.append(entry)
    return battery


BATTERY = _build_battery()


# --------------------------------------------------------------------------
# Candidate-answer validity checks (mechanical, all grounded in SPEC.md).
# --------------------------------------------------------------------------

def _valid_assignment(instance, assignment):
    if not isinstance(assignment, dict):
        return False, "assignment_not_a_dict"
    jobs = set(instance["jobs"])
    if set(assignment.keys()) != jobs:
        return False, "assignment_missing_or_extra_jobs"
    allowed = instance["allowed"]
    for j, m in assignment.items():
        if m not in allowed.get(j, []):
            return False, f"job_{j}_assigned_disallowed_machine_{m}"
    used = {}
    for m in assignment.values():
        used[m] = used.get(m, 0) + 1
    capacity = instance["capacity"]
    for m, n in used.items():
        if n > capacity.get(m, 0):
            return False, f"capacity_exceeded_machine_{m}"
    for pair in instance.get("conflicts", []):
        j1, j2 = pair[0], pair[1]
        if assignment.get(j1) is not None and assignment.get(j1) == assignment.get(j2):
            return False, f"conflict_violated_{j1}_{j2}"
    return True, None


def _valid_certificate(instance, cert):
    if not isinstance(cert, list) or len(cert) == 0:
        return False, "crash:malformed_certificate"
    jobset = set(instance["jobs"])
    if any((not isinstance(j, str)) or j not in jobset for j in cert):
        return False, "crash:malformed_certificate"
    if len(set(cert)) != len(cert):
        return False, "crash:malformed_certificate"
    if oracle.is_feasible(instance, jobs=cert):
        return False, "wrong_certificate"
    for j in cert:
        rest = [x for x in cert if x != j]
        if not oracle.is_feasible(instance, jobs=rest):
            return False, "nonminimal_certificate"
    return True, None


def _check_case(fn, case):
    instance, kind = case["instance"], case["kind"]
    try:
        result = _call_with_timeout(fn, instance)
    except _Timeout:
        return False, "crash:timeout", {}
    except Exception as e:  # noqa: BLE001
        return False, f"crash:{type(e).__name__}", {}

    if not isinstance(result, dict) or "status" not in result:
        return False, "crash:malformed_output", {}
    status = result.get("status")

    if kind == "feasible":
        if status == "optimal":
            ok, why = _valid_assignment(instance, result.get("assignment"))
            if not ok:
                return False, "infeasible_assignment_returned", {"detail": why}
            achieved = sum(instance["cost"][j][result["assignment"][j]] for j in instance["jobs"])
            if achieved != case["true_cost"]:
                return False, "suboptimal_cost", {"achieved": achieved, "true_cost": case["true_cost"]}
            return True, None, {"achieved": achieved}
        elif status == "infeasible":
            return False, "false_infeasibility_claimed", {}
        else:
            return False, "crash:bad_status", {}
    else:  # kind == "infeasible"
        if status == "optimal":
            return False, "missed_infeasibility", {}
        elif status == "infeasible":
            ok, why = _valid_certificate(instance, result.get("certificate"))
            if not ok:
                return False, why, {}
            return True, None, {}
        else:
            return False, "crash:bad_status", {}


def grade(submission_dir):
    result = {"task": "C_prove_it", "passed": False, "checks": {}, "failure_modes": []}

    fn, err = _load_solve(submission_dir)
    if fn is None:
        result["checks"]["load"] = {"passed": False, "detail": err}
        result["failure_modes"].append(f"impl:{err}")
        return result
    result["checks"]["load"] = {"passed": True}

    all_ok = True
    details = {}
    for case in BATTERY:
        ok, mode, extra = _check_case(fn, case)
        details[case["name"]] = {"passed": ok, "kind": case["kind"], "mode": mode, **extra}
        if not ok:
            all_ok = False
            result["failure_modes"].append(f"{case['name']}:{mode}")

    result["checks"]["battery"] = {
        "passed": all_ok,
        "num_cases": len(BATTERY),
        "num_failed": sum(1 for d in details.values() if not d["passed"]),
        "details": details,
    }
    result["passed"] = all_ok
    return result


# --------------------------------------------------------------------------
# Grader-validity gate.
# --------------------------------------------------------------------------

def self_test():
    problems = []

    # (a1) Oracle matches a handful of hand-computed ground-truth instances.
    hand_cases = [
        ({"jobs": ["j0"], "machines": ["m0"], "allowed": {"j0": ["m0"]},
          "capacity": {"m0": 1}, "conflicts": [], "cost": {"j0": {"m0": 5}}}, True, 5),
        ({"jobs": ["j0", "j1"], "machines": ["m0"],
          "allowed": {"j0": ["m0"], "j1": ["m0"]}, "capacity": {"m0": 1},
          "conflicts": [], "cost": {"j0": {"m0": 1}, "j1": {"m0": 1}}}, False, None),
        ({"jobs": ["j0"], "machines": ["m0"], "allowed": {"j0": []},
          "capacity": {"m0": 1}, "conflicts": [], "cost": {"j0": {}}}, False, None),
        ({"jobs": ["j0", "j1"], "machines": ["m0", "m1"],
          "allowed": {"j0": ["m0", "m1"], "j1": ["m0", "m1"]},
          "capacity": {"m0": 1, "m1": 1}, "conflicts": [["j0", "j1"]],
          "cost": {"j0": {"m0": 1, "m1": 1}, "j1": {"m0": 1, "m1": 1}}}, True, 2),
        ({"jobs": ["j0", "j1", "j2"], "machines": ["m0", "m1"],
          "allowed": {"j0": ["m0", "m1"], "j1": ["m0", "m1"], "j2": ["m0", "m1"]},
          "capacity": {"m0": 1, "m1": 1}, "conflicts": [],
          "cost": {"j0": {"m0": 1, "m1": 1}, "j1": {"m0": 1, "m1": 1},
                   "j2": {"m0": 1, "m1": 1}}}, False, None),
    ]
    for inst, exp_feas, exp_cost in hand_cases:
        feas = oracle.is_feasible(inst)
        if feas != exp_feas:
            problems.append(f"oracle feasibility mismatch on hand case {inst['jobs']}: "
                             f"got {feas} expected {exp_feas}")
            continue
        if feas:
            cost, _assignment = oracle.true_optimum(inst)
            if cost != exp_cost:
                problems.append(f"oracle cost mismatch on hand case {inst['jobs']}: "
                                 f"got {cost} expected {exp_cost}")
        else:
            cert = oracle.minimal_infeasible_subset(inst)
            if oracle.is_feasible(inst, jobs=cert):
                problems.append(f"oracle cert not infeasible-by-itself on {inst['jobs']}: {cert}")
            else:
                for j in cert:
                    rest = [x for x in cert if x != j]
                    if not oracle.is_feasible(inst, jobs=rest):
                        problems.append(f"oracle cert not minimal on {inst['jobs']}: {cert}")
                        break

    # (a2) Oracle cross-validated against an independent brute-force search
    # on small random instances.
    rng = random.Random(GROUND_TRUTH_SEED)
    for _ in range(40):
        inst = _small_random_instance(rng)
        bf_feas, bf_cost = oracle.brute_force(inst)
        z_feas = oracle.is_feasible(inst)
        if bf_feas != z_feas:
            problems.append(f"z3/brute-force feasibility mismatch on {inst}")
            continue
        if bf_feas:
            z_cost, _assignment = oracle.true_optimum(inst)
            if z_cost != bf_cost:
                problems.append(f"z3/brute-force cost mismatch on {inst}: z3={z_cost} bf={bf_cost}")
        else:
            cert = oracle.minimal_infeasible_subset(inst)
            if oracle.is_feasible(inst, jobs=cert):
                problems.append(f"oracle cert not infeasible-by-itself on {inst}: {cert}")
            else:
                for j in cert:
                    rest = [x for x in cert if x != j]
                    if not oracle.is_feasible(inst, jobs=rest):
                        problems.append(f"oracle cert not minimal on {inst}: {cert}")
                        break

    # (b) Reference submission must PASS.
    ref = grade(os.path.join(HERE, "reference"))
    if not ref["passed"]:
        problems.append(f"reference did not pass: {ref['failure_modes']}")

    # (c) Known-bad submission (naive conflict-blind greedy) must FAIL.
    bad_greedy = grade(os.path.join(HERE, "known_bad_greedy"))
    if bad_greedy["passed"]:
        problems.append("known_bad_greedy PASSED (should fail)")

    # (d) Trivial do-nothing baseline must FAIL.
    bad_trivial = grade(os.path.join(HERE, "known_bad_trivial"))
    if bad_trivial["passed"]:
        problems.append("known_bad_trivial PASSED (should fail)")

    print(json.dumps({
        "self_test_passed": not problems,
        "problems": problems,
        "battery_size": len(BATTERY),
        "battery_kinds": {c["name"]: c["kind"] for c in BATTERY},
        "reference_passed": ref["passed"],
        "known_bad_greedy_passed": bad_greedy["passed"],
        "known_bad_greedy_failure_modes": bad_greedy["failure_modes"],
        "known_bad_trivial_passed": bad_trivial["passed"],
        "known_bad_trivial_failure_modes": bad_trivial["failure_modes"],
    }, indent=2))
    return 0 if not problems else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--submission")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        sys.exit(self_test())
    if not args.submission:
        ap.error("provide --submission <dir> or --self-test")
    print(json.dumps(grade(args.submission), indent=2))


if __name__ == "__main__":
    main()
