"""Shared verifier machinery for frozen real-repository evolution tasks."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def _copytree(source: Path, target: Path) -> None:
    def ignore(_directory, names):
        return {
            name for name in names
            if name in {"__pycache__", ".pytest_cache", ".mypy_cache", ".venv"}
        }

    shutil.copytree(source, target, ignore=ignore)


def _apply_patch(root: Path, patch: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        ["git", "apply", "--whitespace=nowarn", str(patch)],
        cwd=root, capture_output=True, text=True, timeout=30,
    )
    detail = ((proc.stdout or "") + (proc.stderr or ""))[-2000:]
    return proc.returncode == 0, detail


def _python(root: Path) -> str:
    configured = os.environ.get("KANG_CONAN_PYTHON")
    if configured:
        return configured
    candidate = root / ".venv" / "bin" / "python"
    return str(candidate) if candidate.is_file() else sys.executable


def grade_repo_task(
    *,
    submission_dir: str,
    project_root: Path,
    verifier_dir: Path,
    task_name: str,
    test_targets: list[str],
    timeout: int,
) -> dict:
    result = {
        "task": task_name,
        "passed": False,
        "failure_modes": [],
        "tests": None,
    }
    submission = Path(submission_dir)
    if not (submission / "conan").is_dir() or not (submission / "conans").is_dir():
        result["failure_modes"] = ["impl:missing_conan_source_tree"]
        return result

    temp_parent = Path(tempfile.mkdtemp(prefix=f"{task_name}_grade_"))
    candidate = temp_parent / "candidate"
    try:
        _copytree(submission, candidate)
        ok, detail = _apply_patch(candidate, verifier_dir / "hidden_tests.patch")
        if not ok:
            result["failure_modes"] = ["hidden_tests_patch_conflict"]
            result["tests"] = {"patch_error": detail}
            return result

        command = [_python(project_root), "-m", "pytest", "-q", "--disable-warnings", *test_targets]
        env = dict(os.environ)
        env["PYTHONPATH"] = str(candidate)
        started = time.monotonic()
        try:
            proc = subprocess.run(
                command, cwd=candidate, capture_output=True, text=True,
                timeout=timeout, env=env,
            )
        except subprocess.TimeoutExpired as exc:
            result["failure_modes"] = ["verifier_timeout"]
            result["tests"] = {
                "seconds": timeout,
                "tail": ((exc.stdout or b"") + (exc.stderr or b""))[-3000:].decode(
                    "utf-8", errors="replace"
                ) if isinstance(exc.stdout, bytes) else str(exc.stdout or "")[-3000:],
            }
            return result

        seconds = round(time.monotonic() - started, 3)
        output = (proc.stdout or "") + (proc.stderr or "")
        result["tests"] = {
            "command": command,
            "returncode": proc.returncode,
            "seconds": seconds,
            "tail": output[-6000:],
        }
        if proc.returncode == 0:
            result["passed"] = True
        else:
            result["failure_modes"] = ["hidden_or_regression_tests_failed"]
        return result
    finally:
        shutil.rmtree(temp_parent, ignore_errors=True)


def self_test_repo_task(
    *,
    project_root: Path,
    verifier_dir: Path,
    workspace: Path,
    task_name: str,
    test_targets: list[str],
    timeout: int,
) -> int:
    problems = []
    for patch_name in ("reference.patch", "hidden_tests.patch"):
        patch = verifier_dir / patch_name
        if not patch.is_file() or patch.stat().st_size < 100:
            problems.append(f"missing or empty {patch_name}")

    ref_parent = Path(tempfile.mkdtemp(prefix=f"{task_name}_reference_"))
    reference_dir = ref_parent / "reference"
    try:
        _copytree(workspace, reference_dir)
        ok, patch_error = _apply_patch(reference_dir, verifier_dir / "reference.patch")
        if not ok:
            reference = {"passed": False, "failure_modes": ["reference_patch_conflict"],
                         "tests": {"patch_error": patch_error}}
        else:
            reference = grade_repo_task(
                submission_dir=str(reference_dir), project_root=project_root,
                verifier_dir=verifier_dir, task_name=task_name,
                test_targets=test_targets, timeout=timeout,
            )
        if not reference["passed"]:
            problems.append("reference failed: " + repr(reference.get("failure_modes")))

        baseline = grade_repo_task(
            submission_dir=str(workspace), project_root=project_root,
            verifier_dir=verifier_dir, task_name=task_name,
            test_targets=test_targets, timeout=timeout,
        )
        if baseline["passed"]:
            problems.append("unmodified baseline unexpectedly passed")

        print(json.dumps({
            "self_test_passed": not problems,
            "problems": problems,
            "reference": reference,
            "baseline": baseline,
            "patch_sha256": {
                name: hashlib.sha256((verifier_dir / name).read_bytes()).hexdigest()
                for name in ("reference.patch", "hidden_tests.patch")
            },
        }, indent=2))
        return 0 if not problems else 1
    finally:
        shutil.rmtree(ref_parent, ignore_errors=True)

