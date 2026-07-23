#!/usr/bin/env python3
"""Strict client for the supervisor/executor candidate protocol."""
from __future__ import annotations

import json
import os
import signal
import site
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import isolation

PROTOCOL = "kang-candidate-v2"
WORKER = Path(__file__).with_name("candidate_worker.py").resolve()
EXECUTOR = Path(__file__).with_name("candidate_executor.py").resolve()
RUNTIME_PYTHON = Path(getattr(sys, "_base_executable", sys.executable)).resolve()
MAX_REQUEST_BYTES = 1_048_576
MAX_RESPONSE_BYTES = 1_048_576
MAX_CAPTURE_BYTES = 262_144


@dataclass(frozen=True)
class CandidateResult:
    status: str
    result: Any = None
    error: dict[str, str] | None = None
    worker_pid: int | None = None
    executor_pid: int | None = None
    executor_returncode: int | None = None
    returncode: int | None = None
    supervisor_returncode: int | None = None
    timed_out: bool = False
    stdout: str = ""
    stderr: str = ""
    seconds: float = 0.0
    isolation: str = "strict"

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def _clean_environment(private_dir: Path) -> dict[str, str]:
    runtime_tmp = private_dir / "tmp"
    runtime_home = private_dir / "home"
    runtime_tmp.mkdir(parents=True, exist_ok=True)
    runtime_home.mkdir(parents=True, exist_ok=True)
    keep = ("LANG", "LC_ALL", "LC_CTYPE", "TZ")
    environment = {key: os.environ[key] for key in keep if key in os.environ}
    python_paths = [path for path in site.getsitepackages() if Path(path).exists()]
    environment.update(
        {
            "HOME": str(runtime_home),
            "PATH": "/usr/bin:/bin",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONNOUSERSITE": "1",
            "PYTHONUNBUFFERED": "1",
            "PYTHONPATH": os.pathsep.join(python_paths),
            "TMPDIR": str(runtime_tmp),
            "TMP": str(runtime_tmp),
            "TEMP": str(runtime_tmp),
        }
    )
    return environment


def _error(status: str, message: str, **data: Any) -> CandidateResult:
    return CandidateResult(
        status=status,
        error={"kind": status, "type": status, "message": message},
        **data,
    )


def _validate_response(
    document: Any,
) -> tuple[bool, Any, dict[str, str] | None, int, int | None, int | None, bool]:
    if not isinstance(document, dict):
        raise ValueError("protocol response must be an object")
    common = {
        "protocol",
        "ok",
        "worker_pid",
        "executor_pid",
        "executor_returncode",
        "timed_out",
    }
    expected = common | ({"result"} if document.get("ok") is True else {"error"})
    if set(document) != expected:
        raise ValueError(f"protocol response has unexpected keys: {sorted(set(document) - expected)}")
    if document["protocol"] != PROTOCOL or type(document["ok"]) is not bool:
        raise ValueError("protocol version or ok flag is invalid")
    if type(document["worker_pid"]) is not int or document["worker_pid"] < 1:
        raise ValueError("worker_pid is invalid")
    if document["executor_pid"] is not None and (
        type(document["executor_pid"]) is not int or document["executor_pid"] < 1
    ):
        raise ValueError("executor_pid is invalid")
    if document["executor_returncode"] is not None and type(document["executor_returncode"]) is not int:
        raise ValueError("executor_returncode is invalid")
    if type(document["timed_out"]) is not bool:
        raise ValueError("timed_out is invalid")
    if document["ok"]:
        error = None
        result = document["result"]
    else:
        result = None
        error = document["error"]
        if not isinstance(error, dict) or set(error) != {"kind", "type", "message"}:
            raise ValueError("protocol error object schema is invalid")
        if not all(isinstance(error[key], str) for key in error):
            raise ValueError("protocol error fields must be strings")
    return (
        document["ok"],
        result,
        error,
        document["worker_pid"],
        document["executor_pid"],
        document["executor_returncode"],
        document["timed_out"],
    )


def _validate_result(operation: str, payload: dict[str, Any], result: Any) -> None:
    if operation == "a_compare_batch":
        cases = payload.get("cases")
        if (
            not isinstance(result, list)
            or not isinstance(cases, list)
            or len(result) != len(cases)
            or any(type(value) is not int or value not in {-1, 0, 1} for value in result)
        ):
            raise ValueError("A result must contain one -1/0/1 integer per case")
        return
    if operation == "b_evaluate_batch":
        cases = payload.get("cases")
        if (
            not isinstance(result, list)
            or not isinstance(cases, list)
            or len(result) != len(cases)
            or any(not isinstance(value, list) for value in result)
        ):
            raise ValueError("B result must contain one result list per case")
        return
    if operation == "c_solve":
        if not isinstance(result, dict):
            raise ValueError("C result must be an object")
        return
    if operation == "d_load_invariants":
        if not isinstance(result, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in result.items()
        ):
            raise ValueError("D result must be a string-to-string object")
        return
    raise ValueError(f"unsupported operation: {operation!r}")


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        if process.poll() is None:
            process.kill()


def _read_capture(stream: Any) -> tuple[str, bool]:
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(0)
    raw = stream.read(MAX_CAPTURE_BYTES + 1)
    return raw[:MAX_CAPTURE_BYTES].decode("utf-8", "replace"), size > MAX_CAPTURE_BYTES


def execute(
    operation: str,
    submission: Path,
    payload: dict[str, Any],
    *,
    timeout: float,
    mode: str = "strict",
) -> CandidateResult:
    """Execute one candidate request and normalize every boundary failure."""
    started = time.monotonic()
    submission = submission.resolve()
    request = {
        "protocol": PROTOCOL,
        "operation": operation,
        "submission": str(submission),
        "payload": payload,
    }
    try:
        raw_request = json.dumps(request, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    except (TypeError, ValueError) as exc:
        return _error("protocol_error", f"request is not JSON serializable: {exc}")
    if len(raw_request) > MAX_REQUEST_BYTES:
        return _error("protocol_error", "request exceeds protocol byte limit")
    if timeout <= 0:
        return _error("protocol_error", "timeout must be positive")
    resolution = isolation.resolve(mode)
    if not resolution.available:
        return _error("isolation_error", resolution.error or "isolation unavailable")

    with tempfile.TemporaryDirectory(prefix="kang-candidate-") as private_raw:
        private_dir = Path(private_raw).resolve()
        environment = _clean_environment(private_dir)
        with (
            tempfile.TemporaryFile() as protocol_file,
            tempfile.TemporaryFile() as stdout_file,
            tempfile.TemporaryFile() as stderr_file,
        ):
            command = [
                str(RUNTIME_PYTHON),
                str(WORKER),
                "--protocol-fd",
                str(protocol_file.fileno()),
                "--executor",
                str(EXECUTOR),
                "--private-dir",
                str(private_dir),
                "--timeout",
                str(timeout),
                "--isolation",
                mode,
            ]
            if mode == "strict":
                profile_path = private_dir / "executor.sb"
                profile_path.write_text(
                    isolation.candidate_profile(
                        submission, (EXECUTOR,), private_dir, RUNTIME_PYTHON
                    ),
                    encoding="utf-8",
                )
                command.extend(["--seatbelt-profile", str(profile_path)])
            try:
                process = subprocess.Popen(
                    command,
                    cwd=submission,
                    env=environment,
                    stdin=subprocess.PIPE,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    pass_fds=(protocol_file.fileno(),),
                    start_new_session=True,
                )
                try:
                    process.communicate(raw_request, timeout=timeout + 5)
                except subprocess.TimeoutExpired:
                    _kill_process_group(process)
                    process.wait()
                    stdout, _ = _read_capture(stdout_file)
                    stderr, _ = _read_capture(stderr_file)
                    return _error(
                        "timeout",
                        f"candidate supervisor exceeded {timeout + 5}s",
                        returncode=process.returncode,
                        timed_out=True,
                        stdout=stdout,
                        stderr=stderr,
                        seconds=round(time.monotonic() - started, 3),
                        isolation=mode,
                    )
            except (OSError, subprocess.SubprocessError, isolation.IsolationError) as exc:
                return _error(
                    "isolation_error" if mode == "strict" else "crash",
                    f"{type(exc).__name__}: {exc}",
                    seconds=round(time.monotonic() - started, 3),
                    isolation=mode,
                )

            stdout, stdout_oversized = _read_capture(stdout_file)
            stderr, stderr_oversized = _read_capture(stderr_file)
            protocol_file.seek(0, os.SEEK_END)
            response_size = protocol_file.tell()
            protocol_file.seek(0)
            response_raw = protocol_file.read(MAX_RESPONSE_BYTES + 1)
            common = {
                "returncode": process.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "seconds": round(time.monotonic() - started, 3),
                "isolation": mode,
            }
            if stdout_oversized or stderr_oversized:
                return _error("protocol_error", "supervisor output exceeds capture limit", **common)
            if process.returncode != 0:
                return _error("crash", f"candidate supervisor exited {process.returncode}", **common)
            if response_size > MAX_RESPONSE_BYTES:
                return _error("protocol_error", "protocol response exceeds byte limit", **common)
            try:
                document = json.loads(response_raw)
                (
                    ok,
                    result,
                    error,
                    worker_pid,
                    executor_pid,
                    executor_returncode,
                    timed_out,
                ) = _validate_response(document)
                if ok:
                    _validate_result(operation, payload, result)
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                return _error("protocol_error", f"invalid protocol response: {exc}", **common)
            if ok:
                final_common = dict(common)
                final_common["supervisor_returncode"] = final_common.pop("returncode")
                final_common["returncode"] = executor_returncode
                return CandidateResult(
                    status="ok",
                    result=result,
                    worker_pid=worker_pid,
                    executor_pid=executor_pid,
                    executor_returncode=executor_returncode,
                    timed_out=timed_out,
                    **final_common,
                )
            status = error["kind"] if error["kind"] in {
                "timeout",
                "crash",
                "protocol_error",
                "candidate_error",
            } else "candidate_error"
            # Preserve the public API's historical classification while the
            # structured error retains the more precise output_limit kind.
            if error["kind"] == "output_limit":
                status = "protocol_error"
            final_common = dict(common)
            final_common["supervisor_returncode"] = final_common.pop("returncode")
            final_common["returncode"] = executor_returncode
            return CandidateResult(
                status=status,
                error=error,
                worker_pid=worker_pid,
                executor_pid=executor_pid,
                executor_returncode=executor_returncode,
                timed_out=timed_out,
                **final_common,
            )


def compare_batch(
    submission: Path, cases: list[list[Any]], *, timeout: float, mode: str = "strict"
) -> CandidateResult:
    return execute("a_compare_batch", submission, {"cases": cases}, timeout=timeout, mode=mode)


def evaluate_batch(
    submission: Path, cases: list[dict[str, Any]], *, timeout: float, mode: str = "strict"
) -> CandidateResult:
    return execute("b_evaluate_batch", submission, {"cases": cases}, timeout=timeout, mode=mode)


def solve_one(
    submission: Path, instance: dict[str, Any], *, timeout: float, mode: str = "strict"
) -> CandidateResult:
    return execute("c_solve", submission, {"instance": instance}, timeout=timeout, mode=mode)


def load_invariants(
    submission: Path, *, timeout: float, mode: str = "strict"
) -> CandidateResult:
    return execute("d_load_invariants", submission, {}, timeout=timeout, mode=mode)
