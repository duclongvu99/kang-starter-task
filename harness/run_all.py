#!/usr/bin/env python3
"""Run reproducible, mechanically graded coding-agent experiments.

Every invocation creates a new immutable run directory below ``results/runs``.
Trials are launched only after every selected verifier passes its self-test.
Agent execution and artifact verification are recorded independently: a primary
success requires both a clean agent exit and a passing verifier verdict.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path
from typing import Any

import isolation as process_isolation

ROOT = Path(__file__).resolve().parent.parent
VENV_PY = ROOT / ".venv" / "bin" / "python"
VENV_BIN = ROOT / ".venv" / "bin"
RESULTS = ROOT / "results"
RUNS = RESULTS / "runs"
MAX_PROCESS_LOG_BYTES = 64 * 1024 * 1024

# Both agents receive the same Python environment. The harness itself still
# works with the current interpreter when the project venv is absent, which is
# useful for preflight diagnostics and unit tests.
AGENT_ENV = dict(os.environ)
AGENT_ENV["PATH"] = str(VENV_BIN) + os.pathsep + AGENT_ENV.get("PATH", "")
AGENT_ENV["VIRTUAL_ENV"] = str(ROOT / ".venv")

TASK_DIRS = {
    "A": ROOT / "tasks" / "A_untouchable_oracle",
    "B": ROOT / "tasks" / "B_sqlite_judge",
    "C": ROOT / "tasks" / "C_prove_it",
    "D": ROOT / "tasks" / "D_invariant",
    "E": ROOT / "tasks" / "E_preimage",
}

PROMPT = (
    "You are an autonomous coding agent working in the current working directory, "
    "which contains a self-contained coding task. Read README.md and SPEC.md first, "
    "then complete the task by creating/editing files in this directory. Follow every "
    "rule stated in README.md exactly. Verify your own work as best you can. Do not ask "
    "questions and do not stop early — produce the complete deliverable, then finish."
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _python() -> str:
    return str(VENV_PY) if VENV_PY.exists() else sys.executable


def _write_json(path: Path, data: Any, *, exclusive: bool = False) -> None:
    mode = "x" if exclusive else "w"
    with path.open(mode, encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write("\n")


def create_run_dir(runs_root: Path = RUNS) -> Path:
    """Create and return a collision-resistant run directory."""
    runs_root.mkdir(parents=True, exist_ok=True)
    for _ in range(10):
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        candidate = runs_root / f"{stamp}-{secrets.token_hex(4)}"
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            continue
    raise RuntimeError("could not allocate a unique run directory")


def _terminate_process_group(process: subprocess.Popen[Any]) -> None:
    """Terminate all members of a child's process group, even if its leader exited."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except PermissionError:
        if process.poll() is None:
            process.terminate()
    else:
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.02)
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except PermissionError:
            if process.poll() is None:
                process.kill()
    # Always reap the leader. In particular, killpg may report ESRCH after
    # the leader exits but before its parent has called wait().
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _drain_capped_log(
    pipe: Any,
    log_path: Path,
    cap_bytes: int,
    state: dict[str, Any],
) -> None:
    written = 0
    try:
        with log_path.open("wb") as log:
            while True:
                chunk = pipe.read(64 * 1024)
                if not chunk:
                    break
                remaining = max(0, cap_bytes - written)
                if remaining:
                    kept = chunk[:remaining]
                    log.write(kept)
                    written += len(kept)
                if len(chunk) > remaining:
                    state["overflow"] = True
    except OSError as exc:
        state["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            pipe.close()
        except OSError:
            pass
        state["bytes"] = written


def _run_process(
    cmd: list[str],
    cwd: Path,
    timeout: int,
    log_path: Path,
    *,
    env: dict[str, str] | None = None,
    stdin_devnull: bool = True,
    log_cap_bytes: int = MAX_PROCESS_LOG_BYTES,
) -> dict[str, Any]:
    """Run a command with a complete log unless the explicit cap is exceeded."""
    if log_cap_bytes < 1:
        raise ValueError("log_cap_bytes must be positive")
    started_at = utc_now()
    t0 = time.monotonic()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {
        "command": cmd,
        "started_at": started_at,
        "returncode": None,
        "timed_out": False,
        "execution_error": None,
        "log_overflow": False,
        "log_bytes": 0,
        "log_cap_bytes": log_cap_bytes,
    }
    drain_state: dict[str, Any] = {"overflow": False, "bytes": 0, "error": None}
    drain_thread: threading.Thread | None = None
    try:
        with open(os.devnull, "rb") as devnull:
            process = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                stdin=devnull if stdin_devnull else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            assert process.stdout is not None
            drain_thread = threading.Thread(
                target=_drain_capped_log,
                args=(process.stdout, log_path, log_cap_bytes, drain_state),
                name="harness-log-drain",
                daemon=True,
            )
            drain_thread.start()
            try:
                result["returncode"] = process.wait(timeout=timeout)
                # A CLI can exit after leaving background helpers alive. Kill
                # those helpers before grading or hashing the sandbox.
                _terminate_process_group(process)
            except subprocess.TimeoutExpired:
                result["timed_out"] = True
                _terminate_process_group(process)
                result["returncode"] = process.returncode
    except (OSError, subprocess.SubprocessError) as exc:
        result["execution_error"] = f"{type(exc).__name__}: {exc}"
        if drain_thread is None:
            message = f"\n[harness execution error] {result['execution_error']}\n".encode()
            log_path.write_bytes(message[:log_cap_bytes])
            drain_state["bytes"] = min(len(message), log_cap_bytes)
            drain_state["overflow"] = len(message) > log_cap_bytes
    finally:
        if drain_thread is not None:
            drain_thread.join(timeout=5)
            if drain_thread.is_alive():
                result["execution_error"] = "log drain thread did not terminate"
    result["log_overflow"] = bool(drain_state["overflow"])
    result["log_bytes"] = int(drain_state["bytes"])
    if drain_state.get("error") and result["execution_error"] is None:
        result["execution_error"] = f"log write failed: {drain_state['error']}"
    result["seconds"] = round(time.monotonic() - t0, 3)
    result["finished_at"] = utc_now()
    result["log"] = str(log_path)
    return result


def run_fable(
    sandbox: Path,
    budget: int,
    log_path: Path,
    isolation_mode: str = "strict",
) -> dict[str, Any]:
    cmd = [
        "claude",
        "-p",
        PROMPT,
        "--model",
        "claude-fable-5",
        "--dangerously-skip-permissions",
        "--max-turns",
        "80",
    ]
    runtime_dir = sandbox.parent / "agent-private"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    agent_env = dict(AGENT_ENV)
    agent_env.update(
        {"TMPDIR": str(runtime_dir), "TMP": str(runtime_dir), "TEMP": str(runtime_dir)}
    )
    if isolation_mode == "strict":
        cmd = process_isolation.wrap_command(
            cmd,
            mode="strict",
            profile=process_isolation.agent_profile(sandbox, runtime_dir),
        )
    result = _run_process(cmd, sandbox, budget, log_path, env=agent_env)
    result["isolation"] = process_isolation.resolve(isolation_mode).manifest()
    return result


def run_sol(
    sandbox: Path,
    budget: int,
    log_path: Path,
    isolation_mode: str = "strict",
) -> dict[str, Any]:
    cmd = [
        "codex",
        "exec",
        PROMPT,
        "-C",
        str(sandbox),
        "-s",
        "workspace-write",
        "--skip-git-repo-check",
        "-m",
        "gpt-5.6-sol",
        "-c",
        'model_reasoning_effort="high"',
    ]
    runtime_dir = sandbox.parent / "agent-private"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    agent_env = dict(AGENT_ENV)
    agent_env.update(
        {"TMPDIR": str(runtime_dir), "TMP": str(runtime_dir), "TEMP": str(runtime_dir)}
    )
    if isolation_mode == "strict":
        cmd = process_isolation.wrap_command(
            cmd,
            mode="strict",
            profile=process_isolation.agent_profile(sandbox, runtime_dir),
        )
    result = _run_process(cmd, sandbox, budget, log_path, env=agent_env)
    result["isolation"] = process_isolation.resolve(isolation_mode).manifest()
    return result


AGENTS = {"fable": run_fable, "sol": run_sol}

# These signatures identify failures of the model service/CLI rather than a
# model attempt at the benchmark. Matching is intentionally case-insensitive
# and is performed against the complete log, including successful CLI exits.
AGENT_INFRA_PATTERNS = {
    "session_limit": re.compile(r"(?:hit|reached|exceeded).{0,40}session limit", re.I | re.S),
    "quota": re.compile(r"(?:quota (?:exceeded|exhausted)|insufficient quota|out of quota)", re.I),
    "rate_limit": re.compile(r"(?:rate[- ]limit(?:ed| exceeded)?|too many requests)", re.I),
    "authentication": re.compile(
        r"(?:authentication (?:failed|required|error)|invalid api key|unauthorized|not authenticated)",
        re.I,
    ),
    "network": re.compile(
        r"(?:network (?:error|unavailable)|connection (?:refused|reset|timed out)|"
        r"failed to connect|temporary failure in name resolution)",
        re.I,
    ),
    "api_unavailable": re.compile(
        r"(?:(?:api|service) (?:is )?(?:unavailable|overloaded)|service unavailable|bad gateway)",
        re.I,
    ),
}


def classify_agent_infrastructure(
    agent_run: dict[str, Any], log_path: Path
) -> list[str]:
    """Return infrastructure-failure reasons for an agent invocation."""
    reasons: list[str] = []
    if agent_run.get("execution_error"):
        reasons.append("agent_execution_error")
    if agent_run.get("log_overflow"):
        reasons.append("agent_log_overflow")
    returncode = agent_run.get("returncode")
    if not agent_run.get("timed_out") and returncode is not None and returncode != 0:
        reasons.append("agent_nonzero_exit")
    try:
        output = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        reasons.append(f"agent_log_unreadable:{type(exc).__name__}")
        return reasons
    for name, pattern in AGENT_INFRA_PATTERNS.items():
        if pattern.search(output):
            reasons.append(f"agent_infra_signature:{name}")
    return reasons


def _parse_verdict(output: str) -> dict[str, Any]:
    """Parse the final JSON object printed by a verifier."""
    decoder = json.JSONDecoder()
    candidates: list[dict[str, Any]] = []
    for index, char in enumerate(output):
        if char != "{":
            continue
        try:
            value, consumed = decoder.raw_decode(output[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            if not output[index + consumed :].strip():
                return value
            candidates.append(value)
    if not candidates:
        raise ValueError("verifier did not emit a JSON object")
    verdict_candidates = [item for item in candidates if "passed" in item]
    return verdict_candidates[-1] if verdict_candidates else candidates[-1]


def grade(
    task: str,
    sandbox: Path,
    timeout: int,
    log_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    verify = TASK_DIRS[task] / "verifier" / "verify.py"
    meta = _run_process(
        [_python(), str(verify), "--submission", str(sandbox)],
        ROOT,
        timeout,
        log_path,
        env=AGENT_ENV,
    )
    try:
        output = log_path.read_text(encoding="utf-8", errors="replace")
        if meta["timed_out"]:
            raise TimeoutError(f"verifier exceeded {timeout}s")
        if meta["execution_error"]:
            raise RuntimeError(meta["execution_error"])
        if meta["log_overflow"]:
            raise RuntimeError(
                f"verifier log exceeded {meta['log_cap_bytes']} bytes"
            )
        if meta["returncode"] != 0:
            raise RuntimeError(f"verifier exited {meta['returncode']}")
        verdict = _parse_verdict(output)
        if type(verdict.get("passed")) is not bool:
            raise ValueError("verifier verdict passed field must be an actual boolean")
        meta["completed"] = True
        meta["error"] = None
    except Exception as exc:  # noqa: BLE001 - verifier boundary is untrusted
        meta["completed"] = False
        meta["error"] = f"{type(exc).__name__}: {exc}"
        verdict = {
            "passed": False,
            "failure_modes": ["verifier_error"],
            "verifier_error": meta["error"],
        }
    return verdict, meta


def run_preflight(
    tasks: list[str],
    agents: list[str],
    run_dir: Path,
    timeout: int,
    agent_metadata: dict[str, Any] | None = None,
    isolation_mode: str = "host",
) -> dict[str, Any]:
    """Validate agent executables and verifier self-tests before launching trials."""
    agent_records: dict[str, Any] = {}
    metadata = agent_metadata or {agent: _agent_version(agent) for agent in agents}
    for agent in agents:
        details = metadata.get(agent, {})
        executable = details.get("path")
        executable_ready = bool(
            executable and Path(executable).is_file() and os.access(executable, os.X_OK)
        )
        version_ready = bool(
            details.get("version_returncode") == 0
            and isinstance(details.get("version"), str)
            and details["version"].strip()
            and not details.get("version_error")
        )
        passed = executable_ready and version_ready
        agent_records[agent] = {
            "passed": passed,
            "executable": details.get("executable"),
            "path": executable,
            "version": details.get("version"),
            "version_returncode": details.get("version_returncode"),
            "error": (
                None
                if passed
                else (
                    "agent executable missing or not executable"
                    if not executable_ready
                    else "agent --version failed or returned no version"
                )
            ),
        }

    task_records: dict[str, Any] = {}
    for task in tasks:
        workspace = TASK_DIRS[task] / "workspace"
        workspace_error: str | None = None
        workspace_ready = False
        try:
            if not workspace.is_dir() or workspace.is_symlink():
                raise OSError("workspace is missing, not a directory, or is a symlink")
            preflight_root = run_dir / "preflight"
            preflight_root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=f"copy-{task}-", dir=preflight_root) as raw:
                shutil.copytree(workspace, Path(raw) / "workspace-copy")
            workspace_ready = True
        except OSError as exc:
            workspace_error = f"{type(exc).__name__}: {exc}"
        if not workspace_ready:
            task_records[task] = {
                "passed": False,
                "workspace_ready": False,
                "workspace_error": workspace_error,
                "process_passed": False,
                "self_test_passed": None,
                "parse_error": None,
                "self_test": None,
            }
            continue
        verify = TASK_DIRS[task] / "verifier" / "verify.py"
        log_path = run_dir / "preflight" / f"{task}.log"
        run = _run_process(
            [_python(), str(verify), "--self-test"],
            ROOT,
            timeout,
            log_path,
            env=AGENT_ENV,
        )
        process_passed = (
            not run["timed_out"]
            and not run["log_overflow"]
            and run["execution_error"] is None
            and run["returncode"] == 0
        )
        self_test: dict[str, Any] | None = None
        parse_error: str | None = None
        try:
            self_test = _parse_verdict(log_path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            parse_error = f"{type(exc).__name__}: {exc}"
        passed = process_passed and bool(
            self_test is not None and self_test.get("self_test_passed") is True
        )
        task_records[task] = {
            "passed": passed,
            "workspace_ready": True,
            "workspace_error": None,
            "process_passed": process_passed,
            "self_test_passed": (
                self_test.get("self_test_passed") if self_test is not None else None
            ),
            "parse_error": parse_error,
            "self_test": self_test,
            **run,
        }
    denied_probe_path = TASK_DIRS[tasks[0]] / "verifier" / "verify.py"
    isolation_record = process_isolation.probe(
        isolation_mode,
        run_dir / "preflight" / "isolation_probe",
        denied_probe_path,
    )
    records = {
        "passed": isolation_record.available
        and all(item["passed"] for item in agent_records.values())
        and all(item["passed"] for item in task_records.values()),
        "agents": agent_records,
        "tasks": task_records,
        "isolation": isolation_record.manifest(),
    }
    _write_json(run_dir / "preflight.json", records, exclusive=True)
    return records


def one_trial(
    task: str,
    agent: str,
    number: int,
    budget: int,
    grade_timeout: int,
    run_dir: Path,
    isolation_mode: str = "host",
) -> dict[str, Any]:
    tdir = run_dir / "trials" / task / agent / f"trial_{number}"
    sandbox = tdir / "sandbox"
    tdir.mkdir(parents=True, exist_ok=False)
    shutil.copytree(TASK_DIRS[task] / "workspace", sandbox)

    agent_log = tdir / "agent.log"
    runner = AGENTS[agent]
    if runner is run_fable or runner is run_sol:
        agent_run = runner(sandbox, budget, agent_log, isolation_mode)
    else:
        # Test/local injected runners predate the isolation argument. They are
        # never used by the experiment CLI and retain the small stable hook.
        agent_run = runner(sandbox, budget, agent_log)
    verdict, verifier_run = grade(task, sandbox, grade_timeout, tdir / "verifier.log")

    agent_completed = (
        not agent_run["timed_out"]
        and agent_run["execution_error"] is None
        and agent_run["returncode"] == 0
    )
    artifact_passed = bool(verdict.get("passed"))
    failure_modes = verdict.get("failure_modes", [])
    if not isinstance(failure_modes, list) or any(
        not isinstance(mode, str) for mode in failure_modes
    ):
        failure_modes = ["malformed_verifier_failure_modes"]
    verifier_completed = bool(verifier_run.get("completed"))
    agent_infra_reasons = classify_agent_infrastructure(agent_run, agent_log)
    infra_error = bool(agent_infra_reasons or not verifier_completed)
    trial_valid = not infra_error
    primary_success = (
        trial_valid and agent_completed and verifier_completed and artifact_passed
    )

    reasons: list[str] = []
    if agent_run["timed_out"]:
        reasons.append("agent_timeout")
    reasons.extend(agent_infra_reasons)
    if not verifier_completed:
        reasons.append("verifier_infrastructure_error")
    elif not artifact_passed:
        reasons.append("artifact_failed_verifier")
    if primary_success:
        reasons.append("success")

    status = {
        "agent_completed": agent_completed,
        "artifact_passed_verifier": artifact_passed,
        "verifier_completed": verifier_completed,
        "primary_success": primary_success,
        "infra_error": infra_error,
        "trial_valid": trial_valid,
        "status_reason": reasons,
    }
    record = {
        "task": task,
        "agent": agent,
        "trial": number,
        **status,
        # Backward-compatible alias; unlike the old field this is not merely
        # the verifier verdict.
        "passed": primary_success,
        "failure_modes": failure_modes,
        "timed_out": agent_run["timed_out"],
        "seconds": agent_run["seconds"],
        "returncode": agent_run["returncode"],
    }
    normalized_verdict = dict(verdict)
    normalized_verdict["passed"] = artifact_passed
    normalized_verdict["failure_modes"] = failure_modes
    artifact = {
        "schema_version": 2,
        "record": record,
        "status": status,
        "agent_run": agent_run,
        "verifier_run": verifier_run,
        "verdict": normalized_verdict,
    }
    _write_json(tdir / "verdict.json", artifact, exclusive=True)
    print(
        f"[{task}/{agent}/trial_{number}] primary_success={primary_success} "
        f"artifact_pass={artifact_passed} agent_completed={agent_completed} "
        f"reason={','.join(reasons)} t={agent_run['seconds']}s",
        flush=True,
    )
    return record


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_tree(path: Path) -> str:
    digest = hashlib.sha256()
    for file_path in sorted(p for p in path.rglob("*") if p.is_file()):
        if "__pycache__" in file_path.parts or file_path.suffix == ".pyc":
            continue
        relative = file_path.relative_to(path).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_hash_file(file_path).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _evidence_files(run_dir: Path) -> list[Path]:
    if run_dir.is_symlink() or not run_dir.is_dir():
        raise ValueError("run evidence root must be a real directory, not a symlink")
    files: list[Path] = []
    for current, directories, filenames in os.walk(run_dir, followlinks=False):
        current_path = Path(current)
        for name in directories:
            path = current_path / name
            if path.is_symlink():
                raise ValueError(f"symlink directory forbidden in run evidence: {path}")
        for name in filenames:
            path = current_path / name
            if path.is_symlink():
                raise ValueError(f"symlink file forbidden in run evidence: {path}")
            if not path.is_file():
                raise ValueError(f"non-regular file forbidden in run evidence: {path}")
            files.append(path)
    return sorted(files)


def write_checksums(run_dir: Path) -> Path:
    """Seal every current run output; no run files may be written afterwards."""
    checksum_path = run_dir / "checksums.sha256"
    if checksum_path.exists():
        raise FileExistsError(f"run is already finalized: {checksum_path}")
    files: dict[str, str] = {}
    for path in _evidence_files(run_dir):
        if path != checksum_path:
            files[path.relative_to(run_dir).as_posix()] = _hash_file(path)
    _write_json(
        checksum_path,
        {"algorithm": "sha256", "files": files},
        exclusive=True,
    )
    return checksum_path


def finalize_run(
    run_dir: Path,
    manifest: dict[str, Any],
    state: str,
    **updates: Any,
) -> None:
    if state not in {"completed", "preflight_failed", "aborted"}:
        raise ValueError(f"invalid final run state: {state}")
    manifest.update(updates)
    manifest["state"] = state
    manifest["finished_at"] = utc_now()
    _write_json(run_dir / "manifest.json", manifest)
    write_checksums(run_dir)


def _agent_version(agent: str) -> dict[str, Any]:
    executable = {"fable": "claude", "sol": "codex"}[agent]
    located = shutil.which(executable, path=AGENT_ENV.get("PATH"))
    data: dict[str, Any] = {"executable": executable, "path": located, "version": None}
    if not located:
        return data
    try:
        result = subprocess.run(
            [located, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=5,
            check=False,
        )
        data["version"] = result.stdout.strip() or None
        data["version_returncode"] = result.returncode
    except (OSError, subprocess.SubprocessError) as exc:
        data["version_error"] = f"{type(exc).__name__}: {exc}"
    return data


def build_manifest(args: argparse.Namespace, tasks: list[str], agents: list[str]) -> dict[str, Any]:
    task_hashes = {}
    for task in tasks:
        task_dir = TASK_DIRS[task]
        verifier = task_dir / "verifier" / "verify.py"
        try:
            display_path = str(task_dir.relative_to(ROOT))
        except ValueError:
            display_path = str(task_dir)
        task_hashes[task] = {
            "task_sha256": _hash_tree(task_dir),
            "verifier_sha256": _hash_file(verifier),
            "path": display_path,
        }
    harness_files = [
        Path(__file__).resolve(),
        Path(__file__).with_name("aggregate.py").resolve(),
        Path(__file__).with_name("isolation.py").resolve(),
        Path(__file__).with_name("candidate_client.py").resolve(),
        Path(__file__).with_name("candidate_worker.py").resolve(),
        Path(__file__).with_name("candidate_executor.py").resolve(),
    ]
    isolation_mode = getattr(args, "isolation", "host")
    return {
        "schema_version": 2,
        "created_at": utc_now(),
        "finished_at": None,
        "state": "created",
        "argv": sys.argv,
        "arguments": vars(args),
        "environment": {
            "python": sys.version,
            "python_executable": sys.executable,
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "isolation": process_isolation.resolve(isolation_mode).manifest(),
        "prompt_sha256": hashlib.sha256(PROMPT.encode("utf-8")).hexdigest(),
        "harness_files": {
            path.relative_to(ROOT).as_posix(): _hash_file(path) for path in harness_files
        },
        "agents": {agent: _agent_version(agent) for agent in agents},
        "agent_command_templates": {
            "fable": [
                "claude",
                "-p",
                "<PROMPT>",
                "--model",
                "claude-fable-5",
                "--dangerously-skip-permissions",
                "--max-turns",
                "80",
            ],
            "sol": [
                "codex",
                "exec",
                "<PROMPT>",
                "-C",
                "<SANDBOX>",
                "-s",
                "workspace-write",
                "--skip-git-repo-check",
                "-m",
                "gpt-5.6-sol",
                "-c",
                'model_reasoning_effort="high"',
            ],
        },
        "tasks": task_hashes,
    }


def summarize(records: list[dict[str, Any]], tasks: list[str], agents: list[str]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for task in tasks:
        summary[task] = {}
        for agent in agents:
            rows = [r for r in records if r["task"] == task and r["agent"] == agent]
            successes = sum(bool(r["primary_success"]) for r in rows)
            valid_attempts = sum(bool(r["trial_valid"]) for r in rows)
            artifacts = sum(bool(r["artifact_passed_verifier"]) for r in rows)
            infra_errors = sum(bool(r["infra_error"]) for r in rows)
            modes: dict[str, int] = {}
            for row in rows:
                for mode in row["failure_modes"]:
                    modes[mode] = modes.get(mode, 0) + 1
            summary[task][agent] = {
                "success_rate": successes / valid_attempts if valid_attempts else None,
                "successes": successes,
                "total_trials": len(rows),
                "valid_attempts": valid_attempts,
                "artifact_passes": artifacts,
                "infra_errors": infra_errors,
                "failure_modes": modes,
                "avg_agent_seconds": (
                    round(sum(r["seconds"] for r in rows) / len(rows), 3) if rows else None
                ),
            }
    return summary


def _parse_selection(value: str, label: str) -> list[str]:
    parts = [part.strip() for part in value.split(",")]
    if not parts or any(not part for part in parts):
        raise ValueError(f"--{label} must be a non-empty comma-separated list")
    duplicates = sorted({part for part in parts if parts.count(part) > 1})
    if duplicates:
        raise ValueError(f"--{label} contains duplicates: {duplicates}")
    return parts


def execute(args: argparse.Namespace) -> tuple[Path, int]:
    tasks = _parse_selection(args.tasks, "tasks")
    agents = _parse_selection(args.agents, "agents")
    unknown_tasks = sorted(set(tasks) - set(TASK_DIRS))
    unknown_agents = sorted(set(agents) - set(AGENTS))
    if unknown_tasks or unknown_agents:
        raise ValueError(f"unknown tasks={unknown_tasks}; unknown agents={unknown_agents}")
    isolation_mode = getattr(args, "isolation", "host")
    if isolation_mode not in {"strict", "host"}:
        raise ValueError("--isolation must be one of: strict, host")
    positive_values = {
        "k": args.k,
        "concurrency": args.concurrency,
        "budget": args.budget,
        "grade-timeout": args.grade_timeout,
        "preflight-timeout": args.preflight_timeout,
    }
    invalid = [name for name, value in positive_values.items() if value < 1]
    if invalid:
        raise ValueError(f"these options must be positive: {invalid}")

    runs_root = Path(args.runs_root).resolve() if args.runs_root else RUNS
    run_dir = create_run_dir(runs_root)
    manifest: dict[str, Any] = {
        "schema_version": 2,
        "run_id": run_dir.name,
        "created_at": utc_now(),
        "finished_at": None,
        "state": "created",
    }
    _write_json(run_dir / "manifest.json", manifest, exclusive=True)
    records: list[dict[str, Any]] = []
    try:
        manifest.update(build_manifest(args, tasks, agents))
        manifest["run_id"] = run_dir.name
        _write_json(run_dir / "manifest.json", manifest)

        preflight = run_preflight(
            tasks,
            agents,
            run_dir,
            args.preflight_timeout,
            manifest["agents"],
            isolation_mode,
        )
        manifest["isolation"] = preflight["isolation"]
        _write_json(run_dir / "manifest.json", manifest)
        if not preflight["passed"]:
            failed_tasks = [
                task for task, result in preflight["tasks"].items() if not result["passed"]
            ]
            failed_agents = [
                agent for agent, result in preflight["agents"].items() if not result["passed"]
            ]
            finalize_run(
                run_dir,
                manifest,
                "preflight_failed",
                preflight_failed_tasks=failed_tasks,
                preflight_failed_agents=failed_agents,
                preflight_failed_isolation=(
                    None
                    if preflight["isolation"]["available"]
                    else preflight["isolation"]["error"]
                ),
                preflight_failure_kind=(
                    "isolation"
                    if not preflight["isolation"]["available"]
                    else ("infrastructure" if failed_agents else "verifier")
                ),
            )
            print(
                f"preflight failed for tasks={failed_tasks} agents={failed_agents}; "
                f"no trials launched; run={run_dir}",
                file=sys.stderr,
            )
            return run_dir, 2

        manifest["state"] = "running"
        manifest["preflight_passed_at"] = utc_now()
        _write_json(run_dir / "manifest.json", manifest)
        jobs = [
            (task, agent, number)
            for task in tasks
            for agent in agents
            for number in range(1, args.k + 1)
        ]
        print(
            f"run={run_dir.name} trials={len(jobs)} tasks={tasks} agents={agents} "
            f"k={args.k} budget={args.budget}s concurrency={args.concurrency} "
            f"isolation={isolation_mode}",
            flush=True,
        )

        with cf.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            futures = {
                executor.submit(
                    one_trial,
                    task,
                    agent,
                    number,
                    args.budget,
                    args.grade_timeout,
                    run_dir,
                    isolation_mode,
                ): {"task": task, "agent": agent, "trial": number}
                for task, agent, number in jobs
            }
            for future in cf.as_completed(futures):
                try:
                    records.append(future.result())
                except Exception as exc:  # noqa: BLE001 - preserve failed run evidence
                    for pending in futures:
                        pending.cancel()
                    job = futures[future]
                    raise RuntimeError(f"trial worker failed for {job}: {exc}") from exc

        records.sort(key=lambda row: (row["task"], row["agent"], row["trial"]))
        summary = summarize(records, tasks, agents)
        _write_json(
            run_dir / "summary.json",
            {"summary": summary, "trials": records},
            exclusive=True,
        )
        finalize_run(run_dir, manifest, "completed", trial_count=len(records))
        print("\n===== SUMMARY =====")
        print(json.dumps(summary, indent=2, sort_keys=True))
        return run_dir, 0
    except Exception as exc:  # noqa: BLE001 - every started run must be finalized
        error = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
            "recorded_at": utc_now(),
        }
        if records:
            records.sort(key=lambda row: (row["task"], row["agent"], row["trial"]))
            _write_json(run_dir / "partial_trials.json", records, exclusive=True)
        _write_json(run_dir / "error.json", error, exclusive=True)
        finalize_run(run_dir, manifest, "aborted", error=error, partial_trial_count=len(records))
        print(f"run aborted: {error['message']}; run={run_dir}", file=sys.stderr)
        return run_dir, 3


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", default="A,B,C")
    parser.add_argument("--agents", default="fable,sol")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--budget", type=int, default=900, help="per-attempt wall-clock seconds")
    parser.add_argument("--grade-timeout", type=int, default=300)
    parser.add_argument("--preflight-timeout", type=int, default=300)
    parser.add_argument(
        "--isolation",
        choices=("strict", "host"),
        default="strict",
        help=(
            "strict uses fail-closed macOS Seatbelt; host is an explicitly unsafe "
            "debug mode recorded in the run manifest"
        ),
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="parallel trials (default 1 avoids model/solver resource contention)",
    )
    parser.add_argument("--runs-root", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        _, exit_code = execute(parse_args(argv))
        return exit_code
    except (ValueError, OSError) as exc:
        print(f"harness error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
