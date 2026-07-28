"""Hidden crash-injection verifier for Task J."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TRUSTED_DURABLE = os.path.join(HERE, "durable.py")
GRADE_TIMEOUT = 90

SCENARIOS = [
    {
        "name": "two_party",
        "state": {"accounts": {"alice": 100, "bob": 40}, "applied": {}},
        "head": "a",
        "txid": "rent.2026-07",
        "changes": {"alice": -37, "bob": 37},
    },
    {
        "name": "three_party",
        "state": {"accounts": {"a": 90, "b": 20, "c": 5}, "applied": {}},
        "head": "b",
        "txid": "split_19",
        "changes": {"a": -52, "b": 31, "c": 21},
    },
    {
        "name": "exact_balance_retry",
        "state": {"accounts": {"source": 11, "left": 0, "right": 0}, "applied": {}},
        "head": "a",
        "txid": "all-in",
        "changes": {"source": -11, "left": 6, "right": 5},
    },
    {
        "name": "unicode_accounts_prior_history",
        "state": {
            "accounts": {"Hà Nội": 73, "Đà Nẵng": 20, "東京": 7},
            "applied": {"old-1": "0" * 64, "old-2": "f" * 64},
        },
        "head": "b",
        "txid": "new.tx-3",
        "changes": {"Hà Nội": -29, "Đà Nẵng": 13, "東京": 16},
    },
]

_RUNNER = r'''
import hashlib
import json
import re

from durable import DurableDisk, canonical_json, decode_state, make_image
import solution

SCENARIOS = json.loads({scenarios!r})


def fingerprint(changes):
    return hashlib.sha256(canonical_json(changes).encode("utf-8")).hexdigest()


def expected_post(pre, txid, changes):
    state = {{"accounts": dict(pre["accounts"]), "applied": dict(pre["applied"])}}
    for key, delta in changes.items():
        state["accounts"][key] += delta
    state["applied"][txid] = fingerprint(changes)
    return state


def clean_state(value):
    if type(value) is not dict or set(value) != {{"accounts", "applied"}}:
        raise AssertionError("recover_shape")
    if type(value["accounts"]) is not dict or type(value["applied"]) is not dict:
        raise AssertionError("recover_shape")
    for key, balance in value["accounts"].items():
        if not isinstance(key, str) or type(balance) is not int or balance < 0:
            raise AssertionError("recover_account_type")
    for key, digest in value["applied"].items():
        if not isinstance(key, str) or re.fullmatch(r"[0-9a-f]{{64}}", digest or "") is None:
            raise AssertionError("recover_applied_type")
    return value


def reboot_recover(image):
    disk = DurableDisk(image)
    value = clean_state(solution.recover(disk))
    if disk.mutation_count != 0:
        raise AssertionError("recover_mutated_disk")
    again = clean_state(solution.recover(disk))
    if again != value or disk.mutation_count != 0:
        raise AssertionError("recover_not_idempotent")
    return value


def exercise(sc):
    pre = sc["state"]
    post = expected_post(pre, sc["txid"], sc["changes"])
    initial = make_image(pre, sc["head"])
    if reboot_recover(initial) != pre:
        raise AssertionError("initial_recovery")

    disk = DurableDisk(initial)
    solution.apply(disk, sc["txid"], sc["changes"])
    if not 0 < disk.mutation_count <= 8:
        raise AssertionError("operation_budget")
    if reboot_recover(disk.image()) != post:
        raise AssertionError("not_durable_after_return")

    crash_images = disk.crash_images()
    if not crash_images:
        raise AssertionError("no_crash_boundaries")
    checked = 0
    for cut in crash_images:
        recovered = reboot_recover(cut["image"])
        if recovered != pre and recovered != post:
            raise AssertionError("partial_or_corrupt_state@" + cut["where"])

        retry = DurableDisk(cut["image"])
        solution.apply(retry, sc["txid"], sc["changes"])
        if retry.mutation_count > 8:
            raise AssertionError("retry_operation_budget")
        if reboot_recover(retry.image()) != post:
            raise AssertionError("retry_not_exactly_once@" + cut["where"])
        for retry_cut in retry.crash_images():
            state = reboot_recover(retry_cut["image"])
            if state != recovered and state != post:
                raise AssertionError("retry_partial@" + retry_cut["where"])

        before = retry.mutation_count
        solution.apply(retry, sc["txid"], sc["changes"])
        if retry.mutation_count != before:
            raise AssertionError("successful_retry_wrote_disk")
        if reboot_recover(retry.image()) != post:
            raise AssertionError("successful_retry_changed_state")
        checked += 1
    return {{"crash_images": checked, "mutations": disk.mutation_count}}


def rejection_tests():
    base = {{"accounts": {{"a": 10, "b": 2}}, "applied": {{}}}}
    invalid = [
        ("", {{"a": -1, "b": 1}}),
        ("bad space", {{"a": -1, "b": 1}}),
        (7, {{"a": -1, "b": 1}}),
        ("empty", {{}}),
        ("unknown", {{"a": -1, "z": 1}}),
        ("bool", {{"a": -1, "b": True}}),
        ("zero", {{"a": 0, "b": 0}}),
        ("unbalanced", {{"a": -1, "b": 2}}),
        ("overdraw", {{"a": -11, "b": 11}}),
    ]
    rejected_cls = getattr(solution, "TransactionRejected", None)
    conflict_cls = getattr(solution, "TransactionConflict", None)
    if not isinstance(rejected_cls, type) or not issubclass(rejected_cls, ValueError):
        raise AssertionError("missing_TransactionRejected")
    if not isinstance(conflict_cls, type) or not issubclass(conflict_cls, ValueError):
        raise AssertionError("missing_TransactionConflict")
    for txid, changes in invalid:
        disk = DurableDisk(make_image(base))
        try:
            solution.apply(disk, txid, changes)
        except rejected_cls:
            pass
        except Exception as exc:
            raise AssertionError("wrong_rejection_type:" + type(exc).__name__)
        else:
            raise AssertionError("invalid_accepted")
        if disk.mutation_count != 0 or reboot_recover(disk.image()) != base:
            raise AssertionError("rejection_mutated_disk")

    changes = {{"a": -3, "b": 3}}
    applied = {{"accounts": {{"a": 7, "b": 5}}, "applied": {{"same": fingerprint(changes)}}}}
    disk = DurableDisk(make_image(applied, "b"))
    solution.apply(disk, "same", changes)
    if disk.mutation_count != 0 or reboot_recover(disk.image()) != applied:
        raise AssertionError("idempotent_retry_not_write_free")

    disk = DurableDisk(make_image(applied, "b"))
    try:
        solution.apply(disk, "same", {{"a": -1, "b": 1}})
    except conflict_cls:
        pass
    except Exception as exc:
        raise AssertionError("wrong_conflict_type:" + type(exc).__name__)
    else:
        raise AssertionError("conflict_accepted")
    if disk.mutation_count != 0 or reboot_recover(disk.image()) != applied:
        raise AssertionError("conflict_mutated_disk")


result = {{"passed": False, "failure_modes": [], "scenarios": []}}
try:
    for scenario in SCENARIOS:
        detail = exercise(scenario)
        result["scenarios"].append({{"name": scenario["name"], **detail}})
    rejection_tests()
    result["passed"] = True
except BaseException as exc:
    result["failure_modes"] = [type(exc).__name__ + ":" + str(exc)]
print("RESULT:" + json.dumps(result, sort_keys=True))
'''


def _source_policy(path):
    source = open(path, encoding="utf-8").read()
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"syntax:{exc.msg}"]
    forbidden_imports = {"inspect", "os", "pathlib", "socket", "subprocess"}
    failures = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in forbidden_imports:
                    failures.append("forbidden_import:" + alias.name)
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in forbidden_imports:
                failures.append("forbidden_import:" + (node.module or ""))
        elif isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            if isinstance(node.value, ast.Name) and node.value.id == "disk":
                failures.append("private_disk_access:" + node.attr)
    return sorted(set(failures))


def grade(submission_dir):
    result = {"task": "J_durable_ledger", "passed": False, "failure_modes": [], "detail": None}
    solve_path = os.path.join(submission_dir, "solution.py")
    if not os.path.isfile(solve_path):
        result["failure_modes"] = ["impl:missing_solution_py"]
        return result
    policy = _source_policy(solve_path)
    if policy:
        result["failure_modes"] = policy
        return result

    tmp = tempfile.mkdtemp(prefix="taskJ_grade_")
    try:
        shutil.copy(TRUSTED_DURABLE, os.path.join(tmp, "durable.py"))
        shutil.copy(solve_path, os.path.join(tmp, "solution.py"))
        with open(os.path.join(tmp, "runner.py"), "w", encoding="utf-8") as stream:
            stream.write(_RUNNER.format(scenarios=json.dumps(SCENARIOS, ensure_ascii=False)))
        try:
            proc = subprocess.run(
                [sys.executable, "runner.py"], cwd=tmp, capture_output=True,
                text=True, timeout=GRADE_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            result["failure_modes"] = ["verifier_timeout"]
            return result
        payload = None
        for line in reversed(proc.stdout.splitlines()):
            if line.startswith("RESULT:"):
                payload = json.loads(line[len("RESULT:"):])
                break
        if payload is None:
            tail = (proc.stderr or proc.stdout or "")[-300:].replace("\n", " ")
            result["failure_modes"] = ["crash:" + tail]
            return result
        result["detail"] = payload
        result["passed"] = payload.get("passed") is True
        result["failure_modes"] = payload.get("failure_modes", [])
        return result
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _grade_named(name):
    return grade(os.path.join(HERE, name))


def self_test():
    problems = []
    workspace_copy = os.path.join(HERE, "..", "workspace", "durable.py")
    if hashlib.sha256(open(TRUSTED_DURABLE, "rb").read()).digest() != hashlib.sha256(open(workspace_copy, "rb").read()).digest():
        problems.append("workspace durable.py differs from trusted durable.py")

    reference = _grade_named("reference")
    if not reference["passed"]:
        problems.append("reference failed: " + repr(reference["failure_modes"]))
    expected = {
        "known_bad_in_place": "InvalidRecord",
        "known_bad_publish_first": "InvalidRecord",
        "known_bad_no_idempotence": "not_durable_after_return",
        "known_bad_trivial": "initial_recovery",
    }
    bad_results = {}
    for name, wanted in expected.items():
        verdict = _grade_named(name)
        bad_results[name] = verdict["failure_modes"]
        if verdict["passed"]:
            problems.append(name + " unexpectedly passed")
        elif not any(wanted in mode for mode in verdict["failure_modes"]):
            problems.append(name + " missed expected mode " + wanted + ": " + repr(verdict["failure_modes"]))
    print(json.dumps({
        "self_test_passed": not problems,
        "problems": problems,
        "reference": reference.get("detail"),
        "known_bads": bad_results,
    }, indent=2, ensure_ascii=False))
    return 0 if not problems else 1


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--submission")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.submission:
        parser.error("either --submission or --self-test is required")
    print(json.dumps(grade(args.submission), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
