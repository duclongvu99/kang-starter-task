"""Hidden strong verifier for Task B -- "SQLite is the judge".

Decides PASS/FAIL for a submission directory (a copy of workspace/ after an
agent has worked on it). Two independent, mechanical checks, BOTH required to
pass:

  1. import_scan  -- the submission's evaluate.py must not import (directly,
                     indirectly, or dynamically) any forbidden database /
                     dataframe engine or shell-out mechanism.
  2. behavioral   -- evaluate(db) must agree with an independent, external
                     oracle (real SQLite, executing the exact SQL from
                     SPEC.md) on a held-out battery of fuzzer-generated and
                     hand-picked edge-case databases -- NOT the visible
                     examples.

No LLM judge is involved anywhere. The oracle itself (SQLite) is validated
against hand-derived ground truth for the tricky NULL / multiplicity corners
before it is trusted (grader-validity gate, run by --self-test).

Usage:
  python verify.py --submission <dir>   # grade a submission, prints JSON
  python verify.py --self-test          # validate the oracle + gates
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.join(HERE, "..", "workspace")

FORBIDDEN_MODULES = {
    "sqlite3", "duckdb", "pandas", "polars", "sqlalchemy", "subprocess",
}
FORBIDDEN_ATTRS = {"system", "popen", "popen2", "popen3", "popen4"}

FIXED_SQL = """
SELECT e.name
FROM employees e
JOIN active_departments d ON e.dept_id = d.dept_id
WHERE e.manager_id NOT IN (SELECT banned_id FROM banned_managers)
"""

SEED = 20260719


# --------------------------------------------------------------------------
# The independent oracle: real SQLite executing the literal SQL from SPEC.md.
# --------------------------------------------------------------------------
def oracle_eval(db: dict) -> list:
    con = sqlite3.connect(":memory:")
    try:
        cur = con.cursor()
        cur.execute("CREATE TABLE employees (name TEXT, dept_id INT, manager_id INT)")
        cur.execute("CREATE TABLE active_departments (dept_id INT)")
        cur.execute("CREATE TABLE banned_managers (banned_id INT)")
        for r in db.get("employees", []):
            cur.execute(
                "INSERT INTO employees (name, dept_id, manager_id) VALUES (?, ?, ?)",
                (r.get("name"), r.get("dept_id"), r.get("manager_id")),
            )
        for r in db.get("active_departments", []):
            cur.execute(
                "INSERT INTO active_departments (dept_id) VALUES (?)",
                (r.get("dept_id"),),
            )
        for r in db.get("banned_managers", []):
            cur.execute(
                "INSERT INTO banned_managers (banned_id) VALUES (?)",
                (r.get("banned_id"),),
            )
        rows = cur.execute(FIXED_SQL).fetchall()
        return [row[0] for row in rows]
    finally:
        con.close()


# --------------------------------------------------------------------------
# Fixed, targeted edge-case instances (deterministic).
# --------------------------------------------------------------------------
def _targeted_instances():
    cases = {}

    cases["null_in_banned_excludes_all"] = {
        "employees": [{"name": "Zed", "dept_id": 1, "manager_id": 3}],
        "active_departments": [{"dept_id": 1}],
        "banned_managers": [{"banned_id": 9}, {"banned_id": None}],
    }

    cases["duplicate_dept_multiplicity"] = {
        "employees": [{"name": "Amy", "dept_id": 2, "manager_id": 10}],
        "active_departments": [{"dept_id": 2}, {"dept_id": 2}, {"dept_id": 2}],
        "banned_managers": [],
    }

    cases["null_dept_and_manager_excluded"] = {
        "employees": [
            {"name": "Nan", "dept_id": None, "manager_id": 1},
            {"name": "Mo", "dept_id": 1, "manager_id": None},
        ],
        "active_departments": [{"dept_id": 1}],
        "banned_managers": [{"banned_id": 99}],
    }

    cases["empty_banned_list_includes_null_manager"] = {
        "employees": [{"name": "Alice", "dept_id": 1, "manager_id": None}],
        "active_departments": [{"dept_id": 1}],
        "banned_managers": [],
    }

    cases["null_dept_id_never_joins_null_dept_id"] = {
        "employees": [{"name": "Q", "dept_id": None, "manager_id": 1}],
        "active_departments": [{"dept_id": None}],
        "banned_managers": [],
    }

    cases["empty_everything"] = {
        "employees": [], "active_departments": [], "banned_managers": [],
    }

    return cases


# --------------------------------------------------------------------------
# Single-purpose diagnostic probes: each isolates exactly ONE spec rule so a
# mismatch can be attributed to a specific failure mode.
# --------------------------------------------------------------------------
def _diagnostic_probes():
    return {
        "null_in_not_in": {
            "employees": [{"name": "Zed", "dept_id": 1, "manager_id": 3}],
            "active_departments": [{"dept_id": 1}],
            "banned_managers": [{"banned_id": 9}, {"banned_id": None}],
        },
        "join_multiplicity": {
            "employees": [{"name": "Amy", "dept_id": 2, "manager_id": 10}],
            "active_departments": [{"dept_id": 2}, {"dept_id": 2}, {"dept_id": 2}],
            "banned_managers": [],
        },
        "null_join_key": {
            "employees": [{"name": "Nan", "dept_id": None, "manager_id": 1}],
            "active_departments": [{"dept_id": None}],
            "banned_managers": [],
        },
        "null_manager_id": {
            "employees": [{"name": "Mo", "dept_id": 1, "manager_id": None}],
            "active_departments": [{"dept_id": 1}],
            "banned_managers": [{"banned_id": 99}],
        },
    }


# --------------------------------------------------------------------------
# Fuzzer: random small databases, fixed seed.
# --------------------------------------------------------------------------
def _rand_name(rng):
    if rng.random() < 0.05:
        return None
    return rng.choice("ABCDEFGH") + str(rng.randint(0, 9))


def _rand_id(rng, low, high, null_rate):
    if rng.random() < null_rate:
        return None
    return rng.randint(low, high)


def _rand_db(rng):
    n_emp = rng.randint(0, 6)
    n_dept = rng.randint(0, 5)
    n_ban = rng.randint(0, 4)

    employees = [
        {
            "name": _rand_name(rng),
            "dept_id": _rand_id(rng, 1, 4, null_rate=0.2),
            "manager_id": _rand_id(rng, 1, 5, null_rate=0.2),
        }
        for _ in range(n_emp)
    ]
    active_departments = [
        {"dept_id": _rand_id(rng, 1, 4, null_rate=0.05)} for _ in range(n_dept)
    ]
    banned_managers = [
        {"banned_id": _rand_id(rng, 1, 5, null_rate=0.15)} for _ in range(n_ban)
    ]
    return {
        "employees": employees,
        "active_departments": active_departments,
        "banned_managers": banned_managers,
    }


def _fuzz_bank(n=800, seed=SEED):
    rng = random.Random(seed)
    return [_rand_db(rng) for _ in range(n)]


# --------------------------------------------------------------------------
# Import / forbidden-engine scan (source-level, no execution required).
# --------------------------------------------------------------------------
def _scan_forbidden(source_path):
    if not os.path.exists(source_path):
        return ["file_missing"]
    text = open(source_path, encoding="utf-8", errors="replace").read()
    violations = []
    try:
        tree = ast.parse(text, filename=source_path)
    except SyntaxError as e:
        return [f"syntax_error:{e}"]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in FORBIDDEN_MODULES:
                    violations.append(f"import:{root}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in FORBIDDEN_MODULES:
                violations.append(f"import_from:{root}")
        elif isinstance(node, ast.Call):
            fn = node.func
            # __import__("sqlite3") / importlib.import_module("sqlite3")
            if isinstance(fn, ast.Name) and fn.id == "__import__":
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        if arg.value.split(".")[0] in FORBIDDEN_MODULES:
                            violations.append(f"dynamic_import:{arg.value}")
            if isinstance(fn, ast.Attribute) and fn.attr == "import_module":
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        if arg.value.split(".")[0] in FORBIDDEN_MODULES:
                            violations.append(f"dynamic_import:{arg.value}")
            # os.system(...) / os.popen(...)
            if isinstance(fn, ast.Attribute) and fn.attr in FORBIDDEN_ATTRS:
                violations.append(f"shellout:{fn.attr}")
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRS:
            violations.append(f"shellout_ref:{node.attr}")

    # dedupe, keep order
    seen = []
    for v in violations:
        if v not in seen:
            seen.append(v)
    return seen


# --------------------------------------------------------------------------
# Loading the candidate's evaluate().
# --------------------------------------------------------------------------
def _load_evaluate(submission_dir):
    path = os.path.join(submission_dir, "evaluate.py")
    if not os.path.exists(path):
        return None, "missing_evaluate_py"
    spec = importlib.util.spec_from_file_location("submission_evaluate", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:  # noqa: BLE001
        return None, f"import_error:{type(e).__name__}:{e}"
    fn = getattr(mod, "evaluate", None)
    if not callable(fn):
        return None, "no_evaluate_callable"
    return fn, None


# --------------------------------------------------------------------------
# Behavioral check.
# --------------------------------------------------------------------------
def _behavioral(fn):
    instances = list(_targeted_instances().items())
    for i, db in enumerate(_fuzz_bank()):
        instances.append((f"fuzz_{i}", db))

    checked = 0
    mismatches = []
    for name, db in instances:
        expected = Counter(oracle_eval(db))
        try:
            got_raw = fn(db)
            got = Counter(got_raw)
        except Exception as e:  # noqa: BLE001
            mismatches.append({"case": name, "error": f"raise:{type(e).__name__}:{e}"})
            checked += 1
            continue
        checked += 1
        if got != expected:
            mismatches.append({
                "case": name,
                "expected": sorted(expected.elements(), key=lambda x: (x is None, x)),
                "got": sorted(got.elements(), key=lambda x: (x is None, x)),
            })
    return checked, mismatches


def _diagnose_failure_modes(fn):
    tags = []
    for name, db in _diagnostic_probes().items():
        expected = Counter(oracle_eval(db))
        try:
            got = Counter(fn(db))
        except Exception:  # noqa: BLE001
            tags.append(name)
            continue
        if got != expected:
            tags.append(name)
    return tags


# --------------------------------------------------------------------------
# Grading entry point.
# --------------------------------------------------------------------------
def grade(submission_dir):
    result = {
        "task": "B_sqlite_judge", "passed": False,
        "checks": {}, "failure_modes": [],
    }

    src_path = os.path.join(submission_dir, "evaluate.py")
    violations = _scan_forbidden(src_path)
    result["checks"]["import_scan"] = {"passed": not violations, "violations": violations}
    if violations:
        result["failure_modes"].append("used_forbidden_engine")
        return result  # never even execute a submission that cheats

    fn, err = _load_evaluate(submission_dir)
    if fn is None:
        result["checks"]["behavioral"] = {"passed": False, "detail": err}
        result["failure_modes"].append(f"impl:{err}")
        return result

    checked, mismatches = _behavioral(fn)
    ok_beh = not mismatches
    result["checks"]["behavioral"] = {
        "passed": ok_beh, "checked": checked, "num_mismatches": len(mismatches),
        "examples": mismatches[:5],
    }
    if not ok_beh:
        result["failure_modes"].extend(_diagnose_failure_modes(fn))
        if not result["failure_modes"]:
            result["failure_modes"].append("incorrect_on_held_out")

    result["passed"] = ok_beh
    return result


# --------------------------------------------------------------------------
# Grader-validity gate.
# --------------------------------------------------------------------------
def _oracle_ground_truth_checks():
    """(a) Validate the oracle (SQLite) against hand-derived expected results
    for the tricky corners, so a broken oracle can't silently pass everything."""
    problems = []
    checks = [
        ("null_in_banned_excludes_all", {
            "employees": [{"name": "Zed", "dept_id": 1, "manager_id": 3}],
            "active_departments": [{"dept_id": 1}],
            "banned_managers": [{"banned_id": 9}, {"banned_id": None}],
        }, []),
        ("duplicate_dept_multiplicity", {
            "employees": [{"name": "Amy", "dept_id": 2, "manager_id": 10}],
            "active_departments": [{"dept_id": 2}, {"dept_id": 2}, {"dept_id": 2}],
            "banned_managers": [],
        }, ["Amy", "Amy", "Amy"]),
        ("null_dept_never_joins", {
            "employees": [{"name": "Q", "dept_id": None, "manager_id": 1}],
            "active_departments": [{"dept_id": None}],
            "banned_managers": [],
        }, []),
        ("null_manager_excluded", {
            "employees": [{"name": "Mo", "dept_id": 1, "manager_id": None}],
            "active_departments": [{"dept_id": 1}],
            "banned_managers": [{"banned_id": 99}],
        }, []),
        ("empty_banned_includes_null_manager", {
            "employees": [{"name": "Alice", "dept_id": 1, "manager_id": None}],
            "active_departments": [{"dept_id": 1}],
            "banned_managers": [],
        }, ["Alice"]),
    ]
    for name, db, expected in checks:
        got = oracle_eval(db)
        if Counter(got) != Counter(expected):
            problems.append(f"oracle wrong on {name}: expected {expected}, got {got}")
    return problems


def _shape_trap_confirmed():
    """Confirm known_bad_naive passes the VISIBLE tests (the shape trap)."""
    tmp = tempfile.mkdtemp(prefix="taskB_shapecheck_")
    try:
        shutil.copy(os.path.join(WORKSPACE, "test_visible.py"), tmp)
        shutil.copy(os.path.join(HERE, "known_bad_naive", "evaluate.py"), tmp)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "test_visible.py"],
            cwd=tmp, capture_output=True, text=True,
        )
        return proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def self_test():
    problems = []

    oracle_problems = _oracle_ground_truth_checks()
    problems.extend(oracle_problems)

    ref = grade(os.path.join(HERE, "reference"))
    if not ref["passed"]:
        problems.append(f"reference did not pass: {ref['failure_modes']} {ref['checks']}")

    bad_naive = grade(os.path.join(HERE, "known_bad_naive"))
    if bad_naive["passed"]:
        problems.append("known_bad_naive PASSED (should fail)")

    bad_cheat = grade(os.path.join(HERE, "known_bad_cheat"))
    if bad_cheat["passed"]:
        problems.append("known_bad_cheat PASSED (should fail)")
    elif "used_forbidden_engine" not in bad_cheat["failure_modes"]:
        problems.append(
            f"known_bad_cheat failed for the wrong reason: {bad_cheat['failure_modes']}"
        )

    bad_trivial = grade(os.path.join(HERE, "known_bad_trivial"))
    if bad_trivial["passed"]:
        problems.append("known_bad_trivial PASSED (should fail)")

    shape_ok, shape_detail = _shape_trap_confirmed()
    if not shape_ok:
        problems.append(f"known_bad_naive did NOT pass the visible tests: {shape_detail}")

    print(json.dumps({
        "self_test_passed": not problems,
        "problems": problems,
        "reference_passed": ref["passed"],
        "known_bad_naive_passed": bad_naive["passed"],
        "known_bad_naive_failure_modes": bad_naive["failure_modes"],
        "known_bad_cheat_passed": bad_cheat["passed"],
        "known_bad_cheat_failure_modes": bad_cheat["failure_modes"],
        "known_bad_trivial_passed": bad_trivial["passed"],
        "known_bad_naive_passes_visible_tests": shape_ok,
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
