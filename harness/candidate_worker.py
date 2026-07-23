#!/usr/bin/env python3
"""Trusted supervisor for one untrusted candidate execution.

This process is the only child that receives the final protocol descriptor.
It never imports candidate code.  Candidate code runs in a separate executor
with all non-standard descriptors closed; the supervisor validates the
executor artifact and constructs the final protocol envelope itself.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import resource
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

PROTOCOL = "kang-candidate-v2"
EXECUTOR_PROTOCOL = "kang-executor-v1"
MAX_REQUEST_BYTES = 1_048_576
MAX_RESPONSE_BYTES = 1_048_576
MAX_CAPTURE_BYTES = 262_144
OPERATIONS = {"a_compare_batch", "b_evaluate_batch", "c_solve", "d_load_invariants"}


class RequestError(ValueError):
    pass


def _exact_keys(value: object, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        actual = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise RequestError(f"{label} keys must be {sorted(keys)}, got {actual}")
    return value


def _load_request() -> tuple[dict[str, Any], bytes]:
    raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    if len(raw) > MAX_REQUEST_BYTES:
        raise RequestError("request exceeds byte limit")
    try:
        request = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RequestError(f"request is not valid JSON: {exc}") from exc
    request = _exact_keys(
        request, {"protocol", "operation", "submission", "payload"}, "request"
    )
    if request["protocol"] != PROTOCOL:
        raise RequestError("unsupported protocol version")
    if request["operation"] not in OPERATIONS:
        raise RequestError("unsupported operation")
    if not isinstance(request["submission"], str):
        raise RequestError("submission must be a path string")
    if not isinstance(request["payload"], dict):
        raise RequestError("payload must be an object")
    return request, raw


def _executor_limits(timeout: float):
    def apply() -> None:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(
            resource.RLIMIT_FSIZE, (MAX_CAPTURE_BYTES, MAX_CAPTURE_BYTES)
        )
        cpu_soft = max(1, int(math.ceil(timeout)))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_soft, cpu_soft + 1))
        if hasattr(resource, "RLIMIT_NOFILE"):
            resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
        # RLIMIT_AS is reliable on Linux but destabilizes the macOS Python
        # runtime. Keep a generous address-space cap where it is enforceable.
        if sys.platform.startswith("linux") and hasattr(resource, "RLIMIT_AS"):
            limit = 2 * 1024 * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))

    return apply


def _terminate_and_reap_group(process: subprocess.Popen[bytes]) -> None:
    """Kill the executor group after every outcome, even if its leader exited."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except PermissionError:
        if process.poll() is None:
            process.kill()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _read_capped(path: Path) -> tuple[bytes, bool]:
    size = path.stat().st_size if path.exists() else 0
    with path.open("rb") as stream:
        raw = stream.read(MAX_CAPTURE_BYTES + 1)
    # RLIMIT_FSIZE stops the file exactly at the cap, so equality also means
    # the producer attempted an out-of-bounds write.
    return raw[:MAX_CAPTURE_BYTES], size >= MAX_CAPTURE_BYTES


def _executor_document(path: Path) -> tuple[bool, Any, dict[str, str] | None]:
    if not path.is_file():
        raise ValueError("executor did not produce a result document")
    if path.stat().st_size > MAX_RESPONSE_BYTES:
        raise ValueError("executor result exceeds byte limit")
    try:
        document = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"executor result is invalid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError("executor result must be an object")
    expected = {"executor_protocol", "ok"} | (
        {"result"} if document.get("ok") is True else {"error"}
    )
    if set(document) != expected or document.get("executor_protocol") != EXECUTOR_PROTOCOL:
        raise ValueError("executor result schema/version is invalid")
    if type(document["ok"]) is not bool:
        raise ValueError("executor ok flag is invalid")
    if document["ok"]:
        return True, document["result"], None
    error = document["error"]
    if not isinstance(error, dict) or set(error) != {"kind", "type", "message"}:
        raise ValueError("executor error schema is invalid")
    if not all(isinstance(error[key], str) for key in error):
        raise ValueError("executor error fields must be strings")
    return False, None, error


def _error(kind: str, type_name: str, message: str) -> dict[str, str]:
    return {"kind": kind, "type": type_name, "message": message[:2000]}


def _run_executor(
    raw_request: bytes,
    executor: Path,
    private_dir: Path,
    timeout: float,
    isolation_mode: str,
    seatbelt_profile: Path | None,
) -> dict[str, Any]:
    result_path = private_dir / "executor-result.json"
    stdout_path = private_dir / "candidate.stdout"
    stderr_path = private_dir / "candidate.stderr"
    for path in (result_path, stdout_path, stderr_path):
        path.unlink(missing_ok=True)

    process: subprocess.Popen[bytes] | None = None
    timed_out = False
    try:
        with stdout_path.open("wb") as stdout_file, stderr_path.open("wb") as stderr_file:
            command = [sys.executable, str(executor), "--result", str(result_path)]
            if isolation_mode == "strict":
                if seatbelt_profile is None:
                    raise RequestError("strict executor requires a Seatbelt profile")
                command = ["/usr/bin/sandbox-exec", "-f", str(seatbelt_profile), *command]
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=stdout_file,
                stderr=stderr_file,
                close_fds=True,
                start_new_session=True,
                preexec_fn=_executor_limits(timeout),
            )
            try:
                process.communicate(raw_request, timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "ok": False,
            "error": _error("executor_error", type(exc).__name__, str(exc)),
            "executor_pid": process.pid if process is not None else None,
            "executor_returncode": process.returncode if process is not None else None,
            "timed_out": timed_out,
        }
    finally:
        if process is not None:
            _terminate_and_reap_group(process)

    stdout_raw, stdout_oversized = _read_capped(stdout_path)
    stderr_raw, stderr_oversized = _read_capped(stderr_path)
    # Candidate output is evidence, not protocol. Copy only the bounded bytes
    # after the executor group is dead.
    if stdout_raw:
        sys.stdout.buffer.write(stdout_raw)
        sys.stdout.buffer.flush()
    if stderr_raw:
        sys.stderr.buffer.write(stderr_raw)
        sys.stderr.buffer.flush()

    base = {
        "executor_pid": process.pid,
        "executor_returncode": process.returncode,
        "timed_out": timed_out,
    }
    if timed_out:
        return {
            "ok": False,
            "error": _error("timeout", "TimeoutError", f"candidate exceeded {timeout}s"),
            **base,
        }
    if stdout_oversized or stderr_oversized or process.returncode in {
        -getattr(signal, "SIGXFSZ", 25),
    }:
        return {
            "ok": False,
            "error": _error(
                "output_limit", "OutputLimitError", "candidate stdout/stderr exceeded capture limit"
            ),
            **base,
        }
    if process.returncode != 0:
        return {
            "ok": False,
            "error": _error(
                "crash", "CandidateProcessError", f"executor exited {process.returncode}"
            ),
            **base,
        }
    try:
        ok, result, error = _executor_document(result_path)
    except ValueError as exc:
        return {
            "ok": False,
            "error": _error("protocol_error", type(exc).__name__, str(exc)),
            **base,
        }
    if ok:
        return {"ok": True, "result": result, **base}
    return {"ok": False, "error": error, **base}


def _final_envelope(execution: dict[str, Any]) -> dict[str, Any]:
    common = {
        "protocol": PROTOCOL,
        "ok": execution["ok"],
        "worker_pid": os.getpid(),
        "executor_pid": execution.get("executor_pid"),
        "executor_returncode": execution.get("executor_returncode"),
        "timed_out": bool(execution.get("timed_out")),
    }
    if execution["ok"]:
        common["result"] = execution["result"]
    else:
        common["error"] = execution["error"]
    return common


def _write_protocol(fd: int, document: dict[str, Any]) -> None:
    try:
        raw = json.dumps(document, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raw = json.dumps(
            _final_envelope(
                {
                    "ok": False,
                    "error": _error(
                        "candidate_error",
                        type(exc).__name__,
                        "candidate result is not JSON serializable",
                    ),
                    "executor_pid": document.get("executor_pid"),
                    "executor_returncode": document.get("executor_returncode"),
                    "timed_out": document.get("timed_out", False),
                }
            ),
            separators=(",", ":"),
        ).encode("utf-8")
    if len(raw) > MAX_RESPONSE_BYTES:
        raw = json.dumps(
            _final_envelope(
                {
                    "ok": False,
                    "error": _error(
                        "output_limit",
                        "OutputLimitError",
                        "candidate result exceeds protocol byte limit",
                    ),
                    "executor_pid": document.get("executor_pid"),
                    "executor_returncode": document.get("executor_returncode"),
                    "timed_out": document.get("timed_out", False),
                }
            ),
            separators=(",", ":"),
        ).encode("utf-8")
    view = memoryview(raw)
    while view:
        written = os.write(fd, view)
        view = view[written:]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol-fd", required=True, type=int)
    parser.add_argument("--executor", required=True, type=Path)
    parser.add_argument("--private-dir", required=True, type=Path)
    parser.add_argument("--timeout", required=True, type=float)
    parser.add_argument("--isolation", required=True, choices=("strict", "host"))
    parser.add_argument("--seatbelt-profile", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    os.set_inheritable(args.protocol_fd, False)
    try:
        request, raw_request = _load_request()
        del request  # schema validation only; supervisor never imports candidate code
        private_dir = args.private_dir.resolve()
        private_dir.mkdir(parents=True, exist_ok=True)
        execution = _run_executor(
            raw_request,
            args.executor.resolve(),
            private_dir,
            args.timeout,
            args.isolation,
            args.seatbelt_profile.resolve() if args.seatbelt_profile else None,
        )
    except Exception as exc:  # noqa: BLE001 - trusted boundary must fail closed
        execution = {
            "ok": False,
            "error": _error("request_error", type(exc).__name__, str(exc)),
            "executor_pid": None,
            "executor_returncode": None,
            "timed_out": False,
        }
    try:
        _write_protocol(args.protocol_fd, _final_envelope(execution))
    except OSError:
        return 74
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
