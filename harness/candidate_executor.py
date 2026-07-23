#!/usr/bin/env python3
"""Untrusted candidate executor; deliberately owns no final protocol FD."""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

PROTOCOL = "kang-candidate-v2"
EXECUTOR_PROTOCOL = "kang-executor-v1"
MAX_REQUEST_BYTES = 1_048_576
MAX_RESPONSE_BYTES = 1_048_576
OPERATIONS = {"a_compare_batch", "b_evaluate_batch", "c_solve", "d_load_invariants"}


class RequestError(ValueError):
    pass


def _exact_keys(value: object, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        actual = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise RequestError(f"{label} keys must be {sorted(keys)}, got {actual}")
    return value


def _load_request() -> dict[str, Any]:
    raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    if len(raw) > MAX_REQUEST_BYTES:
        raise RequestError("request exceeds byte limit")
    request = json.loads(raw)
    request = _exact_keys(
        request, {"protocol", "operation", "submission", "payload"}, "request"
    )
    if request["protocol"] != PROTOCOL or request["operation"] not in OPERATIONS:
        raise RequestError("unsupported protocol or operation")
    if not isinstance(request["submission"], str) or not isinstance(request["payload"], dict):
        raise RequestError("invalid submission or payload")
    return request


def _import_candidate(submission: Path, module_name: str) -> Any:
    if not submission.is_dir():
        raise RequestError("submission directory is missing")
    sys.path.insert(0, str(submission))
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def _execute(request: dict[str, Any]) -> Any:
    operation = request["operation"]
    payload = request["payload"]
    submission = Path(request["submission"]).resolve()
    os.chdir(submission)
    if operation == "a_compare_batch":
        payload = _exact_keys(payload, {"cases"}, "A payload")
        cases = payload["cases"]
        if not isinstance(cases, list) or any(
            not isinstance(case, list) or len(case) != 2 for case in cases
        ):
            raise RequestError("A cases must be [left, right] pairs")
        function = getattr(_import_candidate(submission, "semver_compare"), "compare")
        return [function(case[0], case[1]) for case in cases]
    if operation == "b_evaluate_batch":
        payload = _exact_keys(payload, {"cases"}, "B payload")
        if not isinstance(payload["cases"], list):
            raise RequestError("B cases must be a list")
        function = getattr(_import_candidate(submission, "evaluate"), "evaluate")
        return [function(case) for case in payload["cases"]]
    if operation == "c_solve":
        payload = _exact_keys(payload, {"instance"}, "C payload")
        if not isinstance(payload["instance"], dict):
            raise RequestError("C instance must be an object")
        function = getattr(_import_candidate(submission, "solution"), "solve")
        return function(payload["instance"])
    _exact_keys(payload, set(), "D payload")
    invariants = getattr(_import_candidate(submission, "invariants"), "INVARIANTS")
    if not isinstance(invariants, dict):
        raise TypeError("INVARIANTS must be a dictionary")
    return invariants


def _document() -> dict[str, Any]:
    try:
        return {"executor_protocol": EXECUTOR_PROTOCOL, "ok": True, "result": _execute(_load_request())}
    except Exception as exc:  # noqa: BLE001 - untrusted candidate boundary
        return {
            "executor_protocol": EXECUTOR_PROTOCOL,
            "ok": False,
            "error": {
                "kind": "candidate_error",
                "type": type(exc).__name__,
                "message": str(exc)[:2000],
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()
    document = _document()
    try:
        raw = json.dumps(document, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raw = json.dumps(
            {
                "executor_protocol": EXECUTOR_PROTOCOL,
                "ok": False,
                "error": {
                    "kind": "candidate_error",
                    "type": type(exc).__name__,
                    "message": "candidate result is not JSON serializable",
                },
            },
            separators=(",", ":"),
        ).encode("utf-8")
    if len(raw) > MAX_RESPONSE_BYTES:
        raw = json.dumps(
            {
                "executor_protocol": EXECUTOR_PROTOCOL,
                "ok": False,
                "error": {
                    "kind": "output_limit",
                    "type": "OutputLimitError",
                    "message": "candidate result exceeds byte limit",
                },
            },
            separators=(",", ":"),
        ).encode("utf-8")
    args.result.write_bytes(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
