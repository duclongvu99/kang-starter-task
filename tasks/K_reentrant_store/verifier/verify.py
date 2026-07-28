"""Deterministic behavioral verifier for Task K."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TIMEOUT = 60

_RUNNER = r'''
import math
import reactive_store as rs


class BoomA(RuntimeError): pass
class BoomB(LookupError): pass


def check(condition, mode):
    if not condition:
        raise AssertionError(mode)


def basic_transactions():
    store = rs.Store({{"b": 2, "a": 1, "gone": 7}})
    seen = []
    store.watch("*", lambda c: seen.append((c.key, c.old, c.new)))
    with store.transaction():
        store.set("b", 3)
        store.set("a", 9)
        store.set("b", 2)
        store.delete("gone")
        store.set("new", [1, {{"x": True}}])
    check([row[0] for row in seen] == ["a", "gone", "new"], "coalesce_or_sort")
    check(seen[1][2] is rs.MISSING and seen[2][1] is rs.MISSING, "missing_identity")

    with store.transaction():
        store.set("a", 10)
        try:
            with store.transaction():
                store.set("a", 11)
                store.set("inner", 1)
                raise BoomA("inner")
        except BoomA:
            pass
        store.set("outer", 2)
    check(store.snapshot()["a"] == 10 and "inner" not in store.snapshot(), "nested_savepoint")

    before = store.snapshot()
    try:
        with store.transaction():
            store.set("a", 99)
            store.watch("a", lambda c: None)
            raise BoomB("outer")
    except BoomB:
        pass
    check(store.snapshot() == before, "outer_rollback")


def token_rollback():
    store = rs.Store()
    check(store.watch("x", lambda c: None) == 1, "token_start")
    with store.transaction():
        try:
            with store.transaction():
                check(store.watch("x", lambda c: None) == 2, "token_inner")
                raise BoomA()
        except BoomA:
            pass
        check(store.watch("x", lambda c: None) == 2, "token_inner_not_rolled_back")
    try:
        with store.transaction():
            check(store.watch("x", lambda c: None) == 3, "token_outer")
            raise BoomA()
    except BoomA:
        pass
    check(store.watch("x", lambda c: None) == 3, "token_outer_not_rolled_back")


def alias_isolation():
    original = {{"box": [{{"n": 1}}]}}
    store = rs.Store({{"v": original}})
    original["box"][0]["n"] = 99
    check(store.get("v")["box"][0]["n"] == 1, "initial_alias")
    got = store.get("v")
    got["box"].append({{"n": 2}})
    snap = store.snapshot()
    snap["v"]["box"][0]["n"] = 88
    check(store.get("v") == {{"box": [{{"n": 1}}]}}, "read_alias")

    payload = [{{"deep": [1]}}]
    store.set("payload", payload)
    payload[0]["deep"].append(2)
    check(store.get("payload") == [{{"deep": [1]}}], "set_alias")

    observed = []
    def corrupt(change):
        change.new["nested"].append("corrupt")
    def observe(change):
        observed.append(change.new)
    store.watch("obj", corrupt)
    store.watch("obj", observe)
    store.set("obj", {{"nested": ["clean"]}})
    check(observed == [{{"nested": ["clean"]}}], "per_callback_alias")
    check(store.get("obj") == {{"nested": ["clean"]}}, "change_alias_to_store")


def registry_and_reentrancy():
    store = rs.Store({{"x": 0}})
    trace = []
    tokens = {{}}

    def watcher_a(change):
        trace.append(("A", change.key, change.old, change.new))
        if change.key == "x":
            store.watch("y", lambda c: trace.append(("C", c.key, c.old, c.new)))
            store.unwatch(tokens["b"])
            store.set("y", 1)

    def watcher_b(change):
        trace.append(("B", change.key, change.old, change.new))

    tokens["a"] = store.watch("*", watcher_a)
    tokens["b"] = store.watch("*", watcher_b)
    store.set("x", 2)
    check([(x[0], x[1]) for x in trace] == [("A", "x"), ("B", "x"), ("A", "y"), ("C", "y")],
          "wave_registry_snapshot")
    check(store.snapshot() == {{"x": 2, "y": 1}}, "reentrant_state")

    trace.clear()
    def make_z(change):
        if change.key == "start":
            with store.transaction():
                store.set("z", 1)
                try:
                    with store.transaction():
                        store.set("leak", True)
                        raise BoomA()
                except BoomA:
                    pass
                store.set("z", 2)
    store.watch("*", make_z)
    store.set("start", True)
    check(store.get("z") == 2 and store.get("leak") is rs.MISSING, "callback_transaction")


def errors_and_recovery():
    store = rs.Store({{"x": 0}})
    calls = []
    def first(change):
        calls.append("first")
        store.set("side", 1)
        raise BoomA("a")
    def second(change):
        calls.append("second")
        raise BoomB("b")
    def on_side(change):
        calls.append("side")
    store.watch("x", first)
    store.watch("x", second)
    store.watch("side", on_side)
    try:
        store.set("x", 1)
    except rs.DispatchError as exc:
        check(tuple(type(e) for e in exc.errors) == (BoomA, BoomB), "error_order")
        check(tuple(str(e) for e in exc.errors) == ("a", "b"), "original_errors")
    else:
        raise AssertionError("missing_dispatch_error")
    check(calls == ["first", "second", "side"], "error_did_not_continue")
    check(store.snapshot() == {{"x": 1, "side": 1}}, "error_rolled_back_state")
    store.set("ok", 3)
    check(store.get("ok") == 3, "store_not_reusable")


def cycle_limit():
    store = rs.Store({{"x": 0}})
    calls = []
    token = store.watch("x", lambda c: (calls.append(c.new), store.set("x", 1 - c.new)))
    try:
        store.set("x", 1)
    except rs.ReactionCycleError as exc:
        check(exc.pending_keys == ("x",), "cycle_pending_keys")
    else:
        raise AssertionError("missing_cycle_error")
    check(len(calls) == 32, "cycle_wave_count")
    check(store.get("x") == 1, "cycle_retained_wrong_state")
    store.unwatch(token)
    store.set("after", 1)
    check(store.get("after") == 1, "cycle_store_not_reusable")


def validation_and_patterns():
    store = rs.Store({{"x": 1}})
    before = store.snapshot()
    invalid_values = [(1,), float("nan"), float("inf"), {{1: "x"}}]
    class MyList(list): pass
    invalid_values.append(MyList([1]))
    for index, value in enumerate(invalid_values):
        try:
            store.set("bad" + str(index), value)
        except rs.InvalidValue:
            pass
        else:
            raise AssertionError("invalid_value_accepted")
        check(store.snapshot() == before, "invalid_value_mutated")
    for pattern in ("", "a*b", "a**"):
        try: store.watch(pattern, lambda c: None)
        except (ValueError, TypeError): pass
        else: raise AssertionError("invalid_pattern_accepted")
    try: store.watch("x", 7)
    except TypeError: pass
    else: raise AssertionError("noncallable_accepted")

    trace = []
    store.watch("user.*", lambda c: trace.append(c.key))
    with store.transaction():
        store.set("user.name", "n")
        store.set("users.name", "wrong")
    check(trace == ["user.name"], "prefix_matching")

    type_trace = []
    store.watch("num", lambda c: type_trace.append((c.old is rs.MISSING, type(c.old), type(c.new))))
    store.set("num", 1)
    store.set("num", 1.0)
    check(type_trace == [(True, type(rs.MISSING), int), (False, int, float)],
          "type_sensitive_equality")


tests = [basic_transactions, token_rollback, alias_isolation, registry_and_reentrancy,
         errors_and_recovery, cycle_limit, validation_and_patterns]
result = {{"passed": False, "failure_modes": [], "completed": []}}
for test in tests:
    try:
        test()
        result["completed"].append(test.__name__)
    except BaseException as exc:
        result["failure_modes"] = [test.__name__ + ":" + type(exc).__name__ + ":" + str(exc)]
        break
else:
    result["passed"] = True
print("RESULT:" + __import__("json").dumps(result, sort_keys=True))
'''


def grade(submission_dir):
    result = {"task": "K_reentrant_store", "passed": False, "failure_modes": [], "detail": None}
    source = os.path.join(submission_dir, "reactive_store.py")
    if not os.path.isfile(source):
        result["failure_modes"] = ["impl:missing_reactive_store_py"]
        return result
    tmp = tempfile.mkdtemp(prefix="taskK_grade_")
    try:
        shutil.copy(source, os.path.join(tmp, "reactive_store.py"))
        with open(os.path.join(tmp, "runner.py"), "w", encoding="utf-8") as stream:
            stream.write(_RUNNER.replace("{{", "{").replace("}}", "}"))
        try:
            proc = subprocess.run([sys.executable, "runner.py"], cwd=tmp, capture_output=True,
                                  text=True, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            result["failure_modes"] = ["verifier_timeout"]
            return result
        payload = None
        for line in reversed(proc.stdout.splitlines()):
            if line.startswith("RESULT:"):
                payload = json.loads(line[len("RESULT:"):])
                break
        if payload is None:
            result["failure_modes"] = ["crash:" + (proc.stderr or proc.stdout or "")[-300:].replace("\n", " ")]
            return result
        result["detail"] = payload
        result["passed"] = payload.get("passed") is True
        result["failure_modes"] = payload.get("failure_modes", [])
        return result
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def self_test():
    problems = []
    reference = grade(os.path.join(HERE, "reference"))
    if not reference["passed"]:
        problems.append("reference failed: " + repr(reference["failure_modes"]))
    bads = {}
    for name in ("known_bad_eager", "known_bad_shallow", "known_bad_trivial"):
        verdict = grade(os.path.join(HERE, name))
        bads[name] = verdict["failure_modes"]
        if verdict["passed"]:
            problems.append(name + " unexpectedly passed")
    print(json.dumps({"self_test_passed": not problems, "problems": problems,
                      "reference": reference.get("detail"), "known_bads": bads}, indent=2))
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
    print(json.dumps(grade(args.submission), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
