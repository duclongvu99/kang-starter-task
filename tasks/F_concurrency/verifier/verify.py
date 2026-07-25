"""Hidden strong verifier for Task F — Concurrency Correctness.

Grades a submission's `transfer(src, dst, amt)` generator by running it, under a
set of small adversarial scenarios, through an EXHAUSTIVE interleaving model
checker (checker.py) together with a verifier-controlled concurrent auditor. A
correct transaction must, under EVERY interleaving of every scenario:
  - only read/write an account while holding that account's lock,
  - never drive an account negative,
  - never deadlock,
  - be atomic w.r.t. an auditor that snapshots all accounts (no money in flight),
  - and leave the ledger in the unique expected final state.

No LLM judge is involved: the verdict is computed by executing the candidate's
own code under a real, adversarial-but-deterministic scheduler. The candidate is
run OUT OF PROCESS in a throwaway directory containing only trusted copies of the
framework/checker and the candidate's solution.py, so candidate import-time code
cannot introspect this verifier's process (the lesson Task E taught the hard way).
Unlike Task E there is no stealable "answer": knowing the scenarios or the
expected state does not let a racy/deadlocking transfer pass the exhaustive check.

Usage:
  python verify.py --submission <dir>   # grade a submission, prints JSON verdict
  python verify.py --self-test          # grader-validity gate (ref passes, bads fail)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TRUSTED_FRAMEWORK = os.path.join(HERE, "framework.py")
TRUSTED_CHECKER = os.path.join(HERE, "checker.py")
GRADE_TIMEOUT = 120

# Small adversarial scenarios. Each is fully explored (all interleavings) with a
# concurrent auditor appended by the runner. Kept tiny so the search is exhaustive.
SCENARIOS = [
    {"name": "opposite_direction",
     "accounts": {"A": 100, "B": 100},
     "transfers": [["A", "B", 10], ["B", "A", 20]]},
    {"name": "shared_source",
     "accounts": {"A": 100, "B": 100, "C": 100},
     "transfers": [["A", "B", 10], ["A", "C", 20]]},
    {"name": "shared_destination",
     "accounts": {"A": 100, "B": 100, "C": 100},
     "transfers": [["A", "C", 30], ["B", "C", 15]]},
]


def _expected(accounts, transfers):
    end = dict(accounts)
    for src, dst, amt in transfers:
        end[src] -= amt
        end[dst] += amt
    return end


_RUNNER = '''\
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import checker
import solution

SCENARIOS = json.loads({scenarios_json!r})
out = []
for sc in SCENARIOS:
    accounts = sc["accounts"]
    transfers = sc["transfers"]
    expected = sc["expected"]
    names = sorted(accounts)
    total = sum(accounts.values())

    def make(transfers=transfers, names=names, total=total):
        threads = [solution.transfer(s, d, a) for (s, d, a) in transfers]
        threads.append(checker.auditor(names, total))
        return threads

    try:
        violations, nodes = checker.check_scenario(make, accounts, expected)
        vtypes = sorted({{v["type"] for v in violations}})
        out.append({{"name": sc["name"], "ok": not violations,
                     "violation_types": vtypes, "nodes": nodes}})
    except Exception as e:  # candidate blew up the scheduler (e.g. bad op / crash)
        out.append({{"name": sc["name"], "ok": False,
                     "violation_types": ["scenario_error:" + type(e).__name__],
                     "nodes": 0}})
print("RESULT:" + json.dumps(out))
'''


def grade(submission_dir):
    result = {"task": "F_concurrency", "passed": False, "failure_modes": [], "scenarios": []}
    solve_path = os.path.join(submission_dir, "solution.py")
    if not os.path.exists(solve_path):
        result["failure_modes"] = ["impl:missing_solution_py"]
        return result

    scenarios = [dict(sc, expected=_expected(sc["accounts"], sc["transfers"]))
                 for sc in SCENARIOS]
    tmp = tempfile.mkdtemp(prefix="taskF_grade_")
    try:
        shutil.copy(TRUSTED_FRAMEWORK, os.path.join(tmp, "framework.py"))
        shutil.copy(TRUSTED_CHECKER, os.path.join(tmp, "checker.py"))
        shutil.copy(solve_path, os.path.join(tmp, "solution.py"))
        with open(os.path.join(tmp, "runner.py"), "w") as fh:
            fh.write(_RUNNER.format(scenarios_json=json.dumps(scenarios)))
        try:
            proc = subprocess.run([sys.executable, "runner.py"], cwd=tmp,
                                  capture_output=True, text=True, timeout=GRADE_TIMEOUT)
        except subprocess.TimeoutExpired:
            result["failure_modes"] = ["verifier_timeout"]
            return result
        payload = None
        for line in reversed(proc.stdout.splitlines()):
            if line.startswith("RESULT:"):
                payload = json.loads(line[len("RESULT:"):])
                break
        if payload is None:
            tail = (proc.stderr or proc.stdout or "")[-200:]
            result["failure_modes"] = ["crash:" + tail.replace("\n", " ")]
            return result
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    result["scenarios"] = payload
    modes = []
    for sc in payload:
        if not sc["ok"]:
            for vt in sc["violation_types"]:
                modes.append(f"{sc['name']}:{vt}")
    result["passed"] = not modes
    result["failure_modes"] = modes
    return result


def _grade_named(rel):
    return grade(os.path.join(HERE, rel))


def self_test():
    problems = []

    # (0) integrity: the workspace framework the agent develops against must be
    # byte-identical to the trusted framework used at grading time.
    ws_framework = os.path.join(HERE, "..", "workspace", "framework.py")
    if os.path.exists(ws_framework):
        a = hashlib.sha256(open(TRUSTED_FRAMEWORK, "rb").read()).hexdigest()
        b = hashlib.sha256(open(ws_framework, "rb").read()).hexdigest()
        if a != b:
            problems.append("workspace/framework.py differs from verifier/framework.py")

    # (1) the reference solution must PASS every scenario.
    ref = _grade_named(os.path.join("reference"))
    if not ref["passed"]:
        problems.append(f"reference did not pass: {ref['failure_modes']}")

    # (2) each known-bad solution must FAIL, and (3) the trivial baseline must FAIL.
    expect_bad = {
        "known_bad_racy": "unlocked_access",
        "known_bad_deadlock": "deadlock",
        "known_bad_early_release": "audit_saw_inconsistent_total",
        "known_bad_trivial": "wrong_final_state",
    }
    for name, want in expect_bad.items():
        v = _grade_named(name)
        if v["passed"]:
            problems.append(f"{name} unexpectedly PASSED")
        elif not any(want in m for m in v["failure_modes"]):
            problems.append(f"{name} failed but not via '{want}': {v['failure_modes']}")

    print(json.dumps({
        "self_test_passed": not problems,
        "problems": problems,
        "reference_scenarios": ref.get("scenarios"),
    }, indent=2))
    return 0 if not problems else 1


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--submission")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.submission:
        parser.error("either --submission <dir> or --self-test is required")
    print(json.dumps(grade(args.submission), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
