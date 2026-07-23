#!/usr/bin/env python3
"""Seatbelt isolation policies and fail-closed benchmark preflight."""
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = PROJECT_ROOT.parent.resolve()
VENV_ROOT = (PROJECT_ROOT / ".venv").resolve()
SEATBELT = Path("/usr/bin/sandbox-exec")


class IsolationError(RuntimeError):
    pass


def _capabilities(value: bool | None) -> dict[str, bool | None]:
    return {
        "benchmark_secrets_isolated": value,
        "sibling_trials_isolated": value,
        "candidate_isolated": value,
        "candidate_network_isolated": value,
        "candidate_submission_read_only": value,
        "candidate_private_temp_isolated": value,
        # Architecture/unit-test evidence is recorded separately and is not
        # misrepresented as a dynamic preflight observation.
        "candidate_protocol_fd_isolated": False if value is False else None,
        # Native authenticated agent CLIs retain host home/config access.
        "host_filesystem_isolated": False,
        "trial_write_isolated": False,
        "agent_shared_temp_write_isolated": False if value is False else None,
    }


def _evidence(dynamic_passed: bool = False) -> dict[str, object]:
    return {
        "dynamic_probe": (
            [
                "benchmark_secrets_isolated",
                "sibling_trials_isolated",
                "candidate_isolated",
                "candidate_network_isolated",
                "candidate_submission_read_only",
                "candidate_private_temp_isolated",
            ]
            if dynamic_passed
            else []
        ),
        "unit_tested": [
            "candidate_protocol_fd_isolated",
            "candidate_process_group_cleanup",
            "candidate_output_bounded",
        ],
    }


@dataclass(frozen=True)
class IsolationResolution:
    requested: str
    backend: str
    available: bool
    capabilities: dict[str, bool | None] = field(default_factory=dict)
    evidence: dict[str, object] = field(default_factory=dict)
    warning: str | None = None
    error: str | None = None

    def manifest(self) -> dict[str, object]:
        return asdict(self)


def _scheme_string(value: Path | str) -> str:
    return json.dumps(str(value), ensure_ascii=True)


def _resolved_descendant(path: Path, parent: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(parent)
    except ValueError as exc:
        raise IsolationError(f"{label} must be inside {parent}: {resolved}") from exc
    if relative == Path("."):
        raise IsolationError(f"{label} must be a strict descendant of {parent}")
    return resolved


def _resolved_inside(path: Path, parent: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(parent)
    except ValueError as exc:
        raise IsolationError(f"{label} must be inside {parent}: {resolved}") from exc
    return resolved


def _workspace_metadata_ancestors(*paths: Path) -> list[Path]:
    values = {WORKSPACE_ROOT}
    for path in paths:
        current = path if path.is_dir() else path.parent
        while current != WORKSPACE_ROOT:
            try:
                current.relative_to(WORKSPACE_ROOT)
            except ValueError:
                break
            values.add(current)
            current = current.parent
    return sorted(values, key=lambda item: (len(item.parts), str(item)))


def _literal_filters(paths: Sequence[Path]) -> str:
    return " ".join(f"(literal {_scheme_string(path)})" for path in paths)


def _shared_temp_roots() -> list[Path]:
    candidates = {Path("/private/tmp"), Path(tempfile.gettempdir()).resolve()}
    return sorted((path for path in candidates if path.exists()), key=str)


def agent_profile(sandbox: Path, private_temp: Path | None = None) -> str:
    """Workspace-scoped agent policy.

    This protects benchmark secrets and sibling trials. It intentionally does
    not claim whole-host isolation because authenticated native CLIs require
    access to user configuration outside the benchmark workspace.
    """
    allowed = _resolved_descendant(sandbox, WORKSPACE_ROOT, "agent sandbox")
    private = _resolved_descendant(
        private_temp or (allowed / ".agent-private"), WORKSPACE_ROOT, "agent private temp"
    )
    metadata = _literal_filters(_workspace_metadata_ancestors(allowed, private, VENV_ROOT))
    shared_temp_filters = " ".join(
        f"(subpath {_scheme_string(path)})" for path in _shared_temp_roots()
    )
    return "\n".join(
        [
            "(version 1)",
            "(allow default)",
            f"(deny file-read* file-write* (subpath {_scheme_string(WORKSPACE_ROOT)}))",
            f"(deny file-write* {shared_temp_filters})",
            f"(allow file-read-metadata {metadata})",
            f"(allow file-read* (literal {_scheme_string(allowed)}))",
            f"(allow file-read* file-write* (subpath {_scheme_string(allowed)}))",
            f"(allow file-read* (literal {_scheme_string(VENV_ROOT)}))",
            f"(allow file-read* (subpath {_scheme_string(VENV_ROOT)}))",
            f"(allow file-read* file-write* (literal {_scheme_string(private)}))",
            f"(allow file-read* file-write* (subpath {_scheme_string(private)}))",
        ]
    )


def _runtime_root(runtime_python: Path) -> Path:
    resolved = runtime_python.resolve()
    opt_homebrew = Path("/opt/homebrew")
    try:
        resolved.relative_to(opt_homebrew)
        return opt_homebrew
    except ValueError:
        return Path(sys.base_prefix).resolve()


def _external_metadata_ancestors(path: Path) -> list[Path]:
    values: list[Path] = []
    current = path.resolve()
    while current != Path("/"):
        values.append(current)
        current = current.parent
    return list(reversed(values))


def candidate_profile(
    submission: Path,
    trusted_files: Sequence[Path],
    private_temp: Path,
    runtime_python: Path,
) -> str:
    """Default-deny policy for supervisor and inherited candidate executor."""
    allowed_submission = _resolved_descendant(submission, WORKSPACE_ROOT, "submission")
    trusted = [
        _resolved_descendant(path, WORKSPACE_ROOT, "trusted worker") for path in trusted_files
    ]
    private = private_temp.resolve()
    try:
        private.relative_to(WORKSPACE_ROOT)
    except ValueError:
        pass
    else:
        raise IsolationError("candidate private temp must be outside the workspace")
    runtime = runtime_python.resolve()
    runtime_root = _runtime_root(runtime)
    runtime_exec_root = Path(sys.base_prefix).resolve()
    workspace_metadata = _literal_filters(
        _workspace_metadata_ancestors(allowed_submission, VENV_ROOT, *trusted)
    )
    runtime_metadata = _literal_filters(_external_metadata_ancestors(runtime_root))
    return "\n".join(
        [
            "(version 1)",
            "(deny default)",
            '(import "system.sb")',
            "(deny network*)",
            "(allow process-fork)",
            f"(allow process-exec (literal {_scheme_string(runtime)}) "
            f"(subpath {_scheme_string(runtime_exec_root)}))",
            "(allow signal (target self))",
            "(allow sysctl-read)",
            f"(allow file-read* file-map-executable {runtime_metadata} "
            f"(literal {_scheme_string(runtime_root)}) (subpath {_scheme_string(runtime_root)}))",
            f"(allow file-read-metadata {workspace_metadata})",
            f"(allow file-read* (literal {_scheme_string(allowed_submission)}))",
            f"(allow file-read* (subpath {_scheme_string(allowed_submission)}))",
            f"(allow file-read* (literal {_scheme_string(VENV_ROOT)}))",
            f"(allow file-read* (subpath {_scheme_string(VENV_ROOT)}))",
            *[
                f"(allow file-read* (literal {_scheme_string(path)}))" for path in trusted
            ],
            f"(allow file-read* file-write* (literal {_scheme_string(private)}))",
            f"(allow file-read* file-write* (subpath {_scheme_string(private)}))",
        ]
    )


def wrap_command(command: Sequence[str], *, mode: str, profile: str | None = None) -> list[str]:
    if mode == "host":
        return list(command)
    if mode != "strict":
        raise IsolationError(f"unknown isolation mode: {mode!r}")
    if profile is None:
        raise IsolationError("strict isolation requires an explicit Seatbelt profile")
    return [str(SEATBELT), "-p", profile, *command]


def resolve(mode: str) -> IsolationResolution:
    warning = (
        "Benchmark-scoped isolation only: hidden verifier/oracle/reference and sibling "
        "trials are isolated, but authenticated agent CLIs retain host home/config access; "
        "whole-host filesystem and total write isolation are not claimed."
    )
    if mode == "host":
        return IsolationResolution(
            requested="host",
            backend="none-host-process",
            available=True,
            capabilities=_capabilities(False),
            evidence=_evidence(False),
            warning="UNSAFE DEBUG MODE: no benchmark isolation is enforced",
        )
    if mode != "strict":
        raise IsolationError(f"unknown isolation mode: {mode!r}")
    if platform.system() != "Darwin":
        return IsolationResolution(
            requested="strict",
            backend="darwin-seatbelt",
            available=False,
            capabilities=_capabilities(False),
            evidence=_evidence(False),
            warning=warning,
            error="strict isolation currently requires macOS Seatbelt",
        )
    if shutil.which(str(SEATBELT)) is None:
        return IsolationResolution(
            requested="strict",
            backend="darwin-seatbelt",
            available=False,
            capabilities=_capabilities(False),
            evidence=_evidence(False),
            warning=warning,
            error=f"Seatbelt executable not found: {SEATBELT}",
        )
    return IsolationResolution(
        requested="strict",
        backend="darwin-seatbelt",
        available=True,
        capabilities=_capabilities(None),
        evidence=_evidence(False),
        warning=warning,
    )


def _failed(resolution: IsolationResolution, message: str) -> IsolationResolution:
    return IsolationResolution(
        requested=resolution.requested,
        backend=resolution.backend,
        available=False,
        capabilities=_capabilities(False),
        evidence=_evidence(False),
        warning=resolution.warning,
        error=message,
    )


def probe(mode: str, sandbox: Path, denied_path: Path) -> IsolationResolution:
    """Probe both agent and candidate policies before any experiment trial."""
    resolution = resolve(mode)
    if mode == "host" or not resolution.available:
        return resolution
    try:
        allowed = _resolved_descendant(sandbox, WORKSPACE_ROOT, "probe sandbox")
        denied = _resolved_descendant(denied_path, WORKSPACE_ROOT, "probe denied path")
    except IsolationError as exc:
        return _failed(resolution, str(exc))
    allowed.mkdir(parents=True, exist_ok=True)
    sibling = allowed.parent / "isolation_probe_sibling" / "secret.txt"
    sibling.parent.mkdir(parents=True, exist_ok=True)
    sibling.write_text("sibling-secret", encoding="utf-8")
    readable = allowed / "readable.txt"
    readable.write_text("allowed", encoding="utf-8")
    private = allowed.parent / "isolation_probe_agent_private"
    private.mkdir(parents=True, exist_ok=True)
    script = (
        "import json,pathlib,sys; out={}; "
        "\nfor name,path in [('local',sys.argv[1]),('hidden',sys.argv[2]),('sibling',sys.argv[3])]:"
        "\n try: out[name]=pathlib.Path(path).read_text()"
        "\n except OSError: out[name]=None"
        "\nfor name,path in [('hidden_write',sys.argv[2]),('sibling_write',sys.argv[3])]:"
        "\n try: open(path,'a').write('x'); out[name]=True"
        "\n except OSError: out[name]=False"
        "\ntry: pathlib.Path(sys.argv[4]).joinpath('ok').write_text('ok'); out['temp']=True"
        "\nexcept OSError: out['temp']=False"
        "\nprint(json.dumps(out))"
    )
    agent_env = dict(os.environ)
    agent_env.update({"TMPDIR": str(private), "TMP": str(private), "TEMP": str(private)})
    command = wrap_command(
        [sys.executable, "-c", script, str(readable), str(denied), str(sibling), str(private)],
        mode="strict",
        profile=agent_profile(allowed, private),
    )
    try:
        agent_run = subprocess.run(
            command,
            cwd=allowed,
            env=agent_env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=10,
            check=False,
        )
        agent_result = json.loads(agent_run.stdout) if agent_run.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        return _failed(resolution, f"agent Seatbelt probe failed: {type(exc).__name__}: {exc}")
    expected_agent = {
        "local": "allowed",
        "hidden": None,
        "sibling": None,
        "hidden_write": False,
        "sibling_write": False,
        "temp": True,
    }
    if agent_result != expected_agent:
        return _failed(
            resolution,
            f"agent Seatbelt probe exited {agent_run.returncode}: {agent_run.stdout[-1000:]}",
        )

    candidate_submission = allowed.parent / "isolation_probe_candidate"
    candidate_submission.mkdir(parents=True, exist_ok=True)
    candidate_submission.joinpath("local.txt").write_text("candidate-visible", encoding="utf-8")
    candidate_submission.joinpath("solution.py").write_text(
        "from pathlib import Path\n"
        "import os,socket,tempfile\n"
        "def read(path):\n"
        "    try: return Path(path).read_text()\n"
        "    except OSError: return None\n"
        "def write(path):\n"
        "    try: Path(path).write_text('tampered'); return True\n"
        "    except OSError: return False\n"
        "def solve(i):\n"
        "    try:\n"
        "        s=socket.create_connection(('127.0.0.1',i['port']),timeout=.2); s.close(); network=True\n"
        "    except OSError: network=False\n"
        "    p=Path(tempfile.gettempdir())/'candidate-probe'; p.write_text('ok')\n"
        "    return {'local':read(i['local']),'hidden':read(i['hidden']),'sibling':read(i['sibling']),"
        "'submission_write':write(i['local']),'hidden_write':write(i['hidden']),"
        "'sibling_write':write(i['sibling']),'network':network,'temp':p.read_text()}\n",
        encoding="utf-8",
    )
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        import candidate_client

        candidate_result = candidate_client.solve_one(
            candidate_submission,
            {
                "local": str(candidate_submission / "local.txt"),
                "hidden": str(denied),
                "sibling": str(sibling),
                "port": listener.getsockname()[1],
            },
            timeout=5,
            mode="strict",
        )
    finally:
        listener.close()
    expected_candidate = {
        "local": "candidate-visible",
        "hidden": None,
        "sibling": None,
        "submission_write": False,
        "hidden_write": False,
        "sibling_write": False,
        "network": False,
        "temp": "ok",
    }
    if not candidate_result.ok or candidate_result.result != expected_candidate:
        return _failed(resolution, f"candidate Seatbelt probe failed: {candidate_result}")
    return IsolationResolution(
        requested="strict",
        backend="darwin-seatbelt",
        available=True,
        capabilities=_capabilities(True),
        evidence=_evidence(True),
        warning=resolution.warning,
    )
