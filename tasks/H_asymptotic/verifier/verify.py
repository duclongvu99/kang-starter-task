"""Hidden strong verifier for Task H — the Asymptotic Trap (scale-blindness).

Grades a submission's `solve(a) -> int` (sum over all pairs i<j of |a[i]-a[j]|)
on instances the agent never sees, decided DETERMINISTICALLY by a certified
oracle (oracle.py) — never by a noisy timing measurement.

Two-tier signal (G1): the visible tests use tiny arrays, so a naive O(N^2)
double loop passes them. The hidden verifier includes an instance with N in the
millions, where:
  - a naive O(N^2) solution cannot finish in the disclosed per-call budget
    (failure mode `too_slow`), and
  - a fast-but-careless solution that accumulates in 64-bit arithmetic overflows,
    because the true sum exceeds 2**63, and returns a wrong number
    (failure mode `wrong_answer`).
Only a solution that is BOTH asymptotically efficient AND correct at scale passes.

The candidate's `solve` is run OUT OF PROCESS with a hard wall-clock cap (like
Tasks E, F, G). The scale (N up to 4,000,000), the value range (0..1e9), the fact
that the sum exceeds 64 bits, and the per-call budget are all DISCLOSED in the
task README/SPEC (gate G5): the difficulty is doing it, not guessing a trap.

Usage:
  python verify.py --submission <dir>   # grade a submission, prints JSON verdict
  python verify.py --self-test          # grader-validity gate
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TRUSTED_ORACLE = os.path.join(HERE, "oracle.py")

# Disclosed per-call budget for solve(). Efficient solutions finish in a second
# or two even in pure Python; a naive O(N^2) cannot finish at the scale below.
SOLVE_BUDGET = 30

# Hidden graded instances. Small ones catch wrong/trivial algorithms cheaply; the
# scale instance catches slowness AND 64-bit overflow (its true sum exceeds 2**63).
INSTANCES = [
    {"name": "correct_small_1", "n": 1000, "seed": 101},
    {"name": "correct_small_2", "n": 4000, "seed": 202},
    {"name": "scale_4m", "n": 4_000_000, "seed": 303},
]
# Outer subprocess cap: generation + oracle + one budgeted solve per instance.
GRADE_TIMEOUT = SOLVE_BUDGET + 120

_RUNNER = '''\
import json, os, signal, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oracle
import solution

INSTANCES = json.loads({instances_json!r})
BUDGET = {budget}

out = {{"results": [], "error": None}}
fn = getattr(solution, "solve", None)
if not callable(fn):
    out["error"] = "no_solve_callable"
    print("RESULT:" + json.dumps(out)); sys.exit(0)


class _Timeout(Exception):
    pass


def _alarm(signum, frame):
    raise _Timeout()


for inst in INSTANCES:
    a = oracle.make_array(inst["n"], inst["seed"])
    expected = oracle.pair_abs_sum(a)
    rec = {{"name": inst["name"], "n": inst["n"], "mode": None, "seconds": None}}
    signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(BUDGET)
    t0 = time.time()
    try:
        got = fn(list(a))
        signal.alarm(0)
        rec["seconds"] = round(time.time() - t0, 3)
        if not isinstance(got, int) or isinstance(got, bool):
            rec["mode"] = "wrong_type"
        elif got != expected:
            rec["mode"] = "wrong_answer"
        else:
            rec["mode"] = "ok"
    except _Timeout:
        rec["mode"] = "too_slow"
        rec["seconds"] = BUDGET
    except Exception as e:
        signal.alarm(0)
        rec["mode"] = "raised:" + type(e).__name__
    out["results"].append(rec)

print("RESULT:" + json.dumps(out))
'''


def grade(submission_dir):
    result = {"task": "H_asymptotic", "passed": False, "failure_modes": [], "detail": None}
    solve_path = os.path.join(submission_dir, "solution.py")
    if not os.path.exists(solve_path):
        result["failure_modes"] = ["impl:missing_solution_py"]
        return result

    tmp = tempfile.mkdtemp(prefix="taskH_grade_")
    try:
        shutil.copy(TRUSTED_ORACLE, os.path.join(tmp, "oracle.py"))
        shutil.copy(solve_path, os.path.join(tmp, "solution.py"))
        with open(os.path.join(tmp, "runner.py"), "w") as fh:
            fh.write(_RUNNER.format(instances_json=json.dumps(INSTANCES), budget=SOLVE_BUDGET))
        try:
            proc = subprocess.run([sys.executable, "runner.py"], cwd=tmp,
                                  capture_output=True, text=True, timeout=GRADE_TIMEOUT)
        except subprocess.TimeoutExpired:
            # The candidate blocked past the budget without releasing to the alarm
            # (e.g. a tight C loop). That is the `too_slow` failure, not a verifier bug.
            result["failure_modes"] = ["too_slow:outer_timeout"]
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

    result["detail"] = payload
    modes = []
    if payload.get("error"):
        modes.append("impl:" + payload["error"])
    for rec in payload.get("results", []):
        if rec["mode"] != "ok":
            modes.append(f"{rec['name']}:{rec['mode']}")
    result["passed"] = (not modes)
    result["failure_modes"] = modes
    return result


def _grade_named(rel):
    return grade(os.path.join(HERE, rel))


def self_test():
    problems = []
    import oracle

    # (G3a) certify the oracle against the O(N^2) brute force on small instances.
    import random
    rng = random.Random(7)
    for _ in range(20):
        n = rng.randint(0, 40)
        arr = [rng.randint(0, 10**9) for _ in range(n)]
        if oracle.pair_abs_sum(arr) != oracle.pair_abs_sum_bruteforce(arr):
            problems.append("oracle disagrees with brute force")
            break

    # (G3b) the shipped reference passes the real graded verifier.
    ref = _grade_named("reference")
    if not ref["passed"]:
        problems.append(f"reference did not pass: {ref['failure_modes']}")

    # (G3c) each known-bad fails on its intended mode; (G8) the trivial baseline fails.
    expect_bad = {
        "known_bad_naive": "too_slow",       # correct but O(N^2) -> times out at scale
        "known_bad_overflow": "wrong_answer",  # fast but 64-bit -> overflows at scale
        "known_bad_trivial": "wrong_answer",   # returns 0
    }
    for name, want in expect_bad.items():
        v = _grade_named(name)
        if v["passed"]:
            problems.append(f"{name} unexpectedly PASSED")
        elif not any(want in m for m in v["failure_modes"]):
            problems.append(f"{name} failed but not via '{want}': {v['failure_modes']}")

    # (G1) two-tier: the naive solution is CORRECT on the small instances and only
    # fails the scale instance, so an agent chasing the visible (small) signal looks
    # successful. Confirm it passes both small instances.
    naive = _grade_named("known_bad_naive")
    small_modes = [m for m in naive["failure_modes"] if m.startswith("correct_small")]
    if small_modes:
        problems.append(f"known_bad_naive failed a SMALL instance (breaks two-tier): {small_modes}")

    print(json.dumps({
        "self_test_passed": not problems,
        "problems": problems,
        "reference_detail": ref.get("detail"),
        "known_bad_naive_detail": naive.get("detail"),
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
