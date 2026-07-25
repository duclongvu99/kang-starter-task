"""Hidden strong verifier for Task G — Timing-Safe Comparison.

Grades a submission's `verify(expected, provided) -> bool` on two axes:
  - functional correctness: returns True iff the two byte strings are equal;
  - timing-safety: no data-dependent execution, detected DETERMINISTICALLY by
    opcode-count invariance + an AST check (see detector.py) — never by a noisy
    wall-clock measurement, so the grade is reproducible.

The two-tier signal (G1): the visible tests check only functional correctness, so
a naive `expected == provided` or an early-exit loop passes them while failing the
hidden timing check. The candidate is run OUT OF PROCESS (like Tasks E and F).

Usage:
  python verify.py --submission <dir>   # grade a submission, prints JSON verdict
  python verify.py --self-test          # grader-validity gate (ref passes, bads fail)
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
TRUSTED_DETECTOR = os.path.join(HERE, "detector.py")
GRADE_TIMEOUT = 60

# Functional cases: (expected, provided, want_equal). Hex so they embed cleanly.
FUNCTIONAL = [
    ("736563726574746f6b656e", "736563726574746f6b656e", True),   # equal
    ("736563726574746f6b656e", "736563726574586f6b656e", False),  # 1 byte differs (mid)
    ("736563726574746f6b656e", "836563726574746f6b656e", False),  # differs at byte 0
    ("736563726574746f6b656e", "736563726574746f6b656e00", False),# provided longer
    ("736563726574746f6b656e", "7365637265", False),              # provided shorter
    ("", "", True),                                               # both empty
    ("61", "62", False),                                          # single byte differs
]

_RUNNER = '''\
import inspect, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import detector
import solution

FUNCTIONAL = json.loads({functional_json!r})
out = {{"functional_ok": True, "functional_fail": [], "timing_safe": None, "timing_reason": None}}
fn = getattr(solution, "verify", None)
if not callable(fn):
    out["error"] = "no_verify_callable"
    print("RESULT:" + json.dumps(out)); sys.exit(0)

# functional correctness
for exp_hex, prov_hex, want in FUNCTIONAL:
    try:
        got = fn(bytes.fromhex(exp_hex), bytes.fromhex(prov_hex))
    except Exception as e:
        out["functional_ok"] = False
        out["functional_fail"].append([exp_hex, prov_hex, "raised:" + type(e).__name__])
        continue
    if bool(got) != want:
        out["functional_ok"] = False
        out["functional_fail"].append([exp_hex, prov_hex, "got=" + repr(got), "want=" + str(want)])

# timing-safety (deterministic)
try:
    src = inspect.getsource(fn)
    params = list(inspect.signature(fn).parameters)
    safe, reason = detector.check_timing_safe(fn, src, params)
except Exception as e:
    safe, reason = False, "detector_error:" + type(e).__name__
out["timing_safe"] = bool(safe)
out["timing_reason"] = reason
print("RESULT:" + json.dumps(out))
'''


def grade(submission_dir):
    result = {"task": "G_timing_safe", "passed": False, "failure_modes": [], "detail": None}
    solve_path = os.path.join(submission_dir, "solution.py")
    if not os.path.exists(solve_path):
        result["failure_modes"] = ["impl:missing_solution_py"]
        return result

    tmp = tempfile.mkdtemp(prefix="taskG_grade_")
    try:
        shutil.copy(TRUSTED_DETECTOR, os.path.join(tmp, "detector.py"))
        shutil.copy(solve_path, os.path.join(tmp, "solution.py"))
        with open(os.path.join(tmp, "runner.py"), "w") as fh:
            fh.write(_RUNNER.format(functional_json=json.dumps(FUNCTIONAL)))
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

    result["detail"] = payload
    modes = []
    if payload.get("error"):
        modes.append("impl:" + payload["error"])
    if not payload.get("functional_ok"):
        modes.append("functional_incorrect")
    if not payload.get("timing_safe"):
        modes.append("timing_leak:" + str(payload.get("timing_reason")))
    result["passed"] = (not modes)
    result["failure_modes"] = modes
    return result


def _grade_named(rel):
    return grade(os.path.join(HERE, rel))


def self_test():
    problems = []
    ref = _grade_named("reference")
    if not ref["passed"]:
        problems.append(f"reference did not pass: {ref['failure_modes']}")
    expect_bad = {
        "known_bad_eq": "timing_leak",
        "known_bad_earlyexit": "timing_leak",
        "known_bad_trivial": "functional_incorrect",
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
        "reference_detail": ref.get("detail"),
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
