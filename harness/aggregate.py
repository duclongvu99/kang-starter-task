#!/usr/bin/env python3
"""Validate and aggregate one explicitly selected immutable experiment run."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

TASK_LABEL = {
    "A": "A: reward-hacking oracle",
    "B": "B: SQL NULL/multiplicity",
    "C": "C: Z3-certified optimization",
    "D": "D: loop-invariant synthesis",
    "E": "E: preimage (search-hard)",
    "F": "F: concurrency correctness",
    "G": "G: timing-safe comparison",
    "H": "H: asymptotic trap (scale)",
    "I": "I: exploit-chain (logic flaws)",
}


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_symlink():
        digest.update(b"symlink\0")
        digest.update(os.fsencode(os.readlink(path)))
        return digest.hexdigest()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _evidence_files(run_dir: Path) -> list[Path]:
    if run_dir.is_symlink() or not run_dir.is_dir():
        raise ValueError("run evidence root must be a real directory, not a symlink")
    files: list[Path] = []
    for current, directories, filenames in os.walk(run_dir, followlinks=False):
        current_path = Path(current)
        for name in list(directories):
            path = current_path / name
            if path.is_symlink():
                files.append(path)
                directories.remove(name)
        for name in filenames:
            path = current_path / name
            if not path.is_symlink() and not path.is_file():
                raise ValueError(f"non-regular file forbidden in run evidence: {path}")
            files.append(path)
    return sorted(files)


def verify_checksums(run_dir: Path) -> None:
    evidence_files = _evidence_files(run_dir)
    checksum_path = run_dir / "checksums.sha256"
    if not checksum_path.is_file():
        raise ValueError("run is not finalized: missing checksums.sha256")
    try:
        document = json.loads(checksum_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid checksums.sha256: {exc}") from exc
    if document.get("algorithm") != "sha256" or not isinstance(document.get("files"), dict):
        raise ValueError("invalid checksums.sha256 schema")

    expected: dict[str, str] = document["files"]
    actual_paths = {
        path.relative_to(run_dir).as_posix()
        for path in evidence_files
        if path != checksum_path
    }
    if actual_paths != set(expected):
        missing = sorted(set(expected) - actual_paths)
        unexpected = sorted(actual_paths - set(expected))
        raise ValueError(f"checksum file set mismatch: missing={missing}, unexpected={unexpected}")
    mismatched = [
        relative
        for relative, digest in sorted(expected.items())
        if _hash_file(run_dir / relative) != digest
    ]
    if mismatched:
        raise ValueError(f"checksum mismatch: {mismatched}")


def _selection(value: Any, label: str) -> list[str]:
    if not isinstance(value, str):
        raise ValueError(f"manifest arguments.{label} must be a string")
    parts = [part.strip() for part in value.split(",")]
    if not parts or any(not part for part in parts) or len(set(parts)) != len(parts):
        raise ValueError(f"manifest arguments.{label} is empty or contains duplicates")
    return parts


def _actual_bool(container: dict[str, Any], field: str, label: str) -> bool:
    value = container.get(field)
    if type(value) is not bool:
        raise ValueError(f"{label}.{field} must be an actual boolean")
    return value


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a list of strings")
    return value


def _validate_trial_document(data: Any, label: str) -> None:
    if not isinstance(data, dict) or data.get("schema_version") != 2:
        raise ValueError(f"{label} must be a schema_version 2 object")
    record = data.get("record")
    status = data.get("status")
    verdict = data.get("verdict")
    agent_run = data.get("agent_run")
    verifier_run = data.get("verifier_run")
    if not all(
        isinstance(value, dict)
        for value in (record, status, verdict, agent_run, verifier_run)
    ):
        raise ValueError(f"{label} record/status/run/verdict sections must be objects")
    assert isinstance(record, dict)
    assert isinstance(status, dict)
    assert isinstance(verdict, dict)
    assert isinstance(agent_run, dict)
    assert isinstance(verifier_run, dict)

    if not isinstance(record.get("task"), str) or not record["task"]:
        raise ValueError(f"{label}.record.task must be a non-empty string")
    if not isinstance(record.get("agent"), str) or not record["agent"]:
        raise ValueError(f"{label}.record.agent must be a non-empty string")
    if type(record.get("trial")) is not int or record["trial"] < 1:
        raise ValueError(f"{label}.record.trial must be a positive integer")

    boolean_fields = (
        "agent_completed",
        "artifact_passed_verifier",
        "verifier_completed",
        "primary_success",
        "infra_error",
        "trial_valid",
    )
    values = {field: _actual_bool(record, field, f"{label}.record") for field in boolean_fields}
    for field in boolean_fields:
        status_value = _actual_bool(status, field, f"{label}.status")
        if status_value is not values[field]:
            raise ValueError(f"{label} record/status mismatch for {field}")
    if _actual_bool(record, "passed", f"{label}.record") is not values["primary_success"]:
        raise ValueError(f"{label}.record.passed must equal primary_success")
    if values["trial_valid"] is values["infra_error"]:
        raise ValueError(f"{label} trial_valid must be the inverse of infra_error")
    if values["primary_success"] and not (
        values["trial_valid"]
        and values["agent_completed"]
        and values["verifier_completed"]
        and values["artifact_passed_verifier"]
        and not values["infra_error"]
    ):
        raise ValueError(f"{label} primary_success violates trial semantics")

    verdict_passed = _actual_bool(verdict, "passed", f"{label}.verdict")
    if verdict_passed is not values["artifact_passed_verifier"]:
        raise ValueError(f"{label} verifier verdict disagrees with artifact status")
    verifier_completed = _actual_bool(verifier_run, "completed", f"{label}.verifier_run")
    if verifier_completed is not values["verifier_completed"]:
        raise ValueError(f"{label} verifier completion status is inconsistent")
    agent_timed_out = _actual_bool(agent_run, "timed_out", f"{label}.agent_run")
    if _actual_bool(record, "timed_out", f"{label}.record") is not agent_timed_out:
        raise ValueError(f"{label} agent timeout status is inconsistent")
    execution_error = agent_run.get("execution_error")
    if execution_error is not None and not isinstance(execution_error, str):
        raise ValueError(f"{label}.agent_run.execution_error must be null or string")
    returncode = agent_run.get("returncode")
    if returncode is not None and type(returncode) is not int:
        raise ValueError(f"{label}.agent_run.returncode must be null or integer")
    expected_agent_completed = (
        not agent_timed_out and execution_error is None and returncode == 0
    )
    if values["agent_completed"] is not expected_agent_completed:
        raise ValueError(f"{label} agent_completed is inconsistent with agent_run")

    reasons = _string_list(record.get("status_reason"), f"{label}.record.status_reason")
    if _string_list(status.get("status_reason"), f"{label}.status.status_reason") != reasons:
        raise ValueError(f"{label} record/status reasons disagree")
    modes = _string_list(record.get("failure_modes"), f"{label}.record.failure_modes")
    if _string_list(verdict.get("failure_modes"), f"{label}.verdict.failure_modes") != modes:
        raise ValueError(f"{label} record/verdict failure modes disagree")
    seconds = agent_run.get("seconds")
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or seconds < 0:
        raise ValueError(f"{label}.agent_run.seconds must be nonnegative numeric")
    record_seconds = record.get("seconds")
    if isinstance(record_seconds, bool) or not isinstance(record_seconds, (int, float)):
        raise ValueError(f"{label}.record.seconds must be numeric")
    if record_seconds != seconds:
        raise ValueError(f"{label} record/agent seconds disagree")
    if record.get("returncode") != returncode or (
        record.get("returncode") is not None and type(record.get("returncode")) is not int
    ):
        raise ValueError(f"{label} record/agent returncode disagrees")


def _load_and_validate_trials(
    run_dir: Path,
    manifest: dict[str, Any],
    allow_incomplete: bool,
) -> list[dict[str, Any]]:
    arguments = manifest.get("arguments")
    if not isinstance(arguments, dict):
        raise ValueError("manifest is missing arguments")
    tasks = _selection(arguments.get("tasks"), "tasks")
    agents = _selection(arguments.get("agents"), "agents")
    k = arguments.get("k")
    if not isinstance(k, int) or isinstance(k, bool) or k < 1:
        raise ValueError("manifest arguments.k must be a positive integer")
    expected = {
        (task, agent, number)
        for task in tasks
        for agent in agents
        for number in range(1, k + 1)
    }

    trial_root = run_dir / "trials"
    trial_dirs = sorted(trial_root.glob("*/*/trial_*")) if trial_root.exists() else []
    data_rows: list[dict[str, Any]] = []
    found: set[tuple[str, str, int]] = set()
    problems: list[str] = []
    for trial_dir in trial_dirs:
        if not trial_dir.is_dir():
            continue
        task = trial_dir.parts[-3]
        agent = trial_dir.parts[-2]
        suffix = trial_dir.name.removeprefix("trial_")
        if not suffix.isdigit() or int(suffix) < 1:
            problems.append(f"malformed trial directory: {trial_dir.relative_to(run_dir)}")
            continue
        path_key = (task, agent, int(suffix))
        verdict_file = trial_dir / "verdict.json"
        if not verdict_file.is_file():
            problems.append(f"missing verdict.json: {trial_dir.relative_to(run_dir)}")
            continue
        try:
            data = json.loads(verdict_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"invalid verdict {verdict_file.relative_to(run_dir)}: {exc}")
            continue
        try:
            _validate_trial_document(data, verdict_file.relative_to(run_dir).as_posix())
        except ValueError as exc:
            problems.append(str(exc))
            continue
        record = data.get("record")
        if not isinstance(record, dict):
            problems.append(f"missing record: {verdict_file.relative_to(run_dir)}")
            continue
        record_key = (record.get("task"), record.get("agent"), record.get("trial"))
        if record_key != path_key:
            problems.append(
                f"trial identity mismatch at {verdict_file.relative_to(run_dir)}: "
                f"path={path_key}, record={record_key}"
            )
            continue
        if record_key in found:
            problems.append(f"duplicate trial identity: {record_key}")
            continue
        found.add(record_key)
        data_rows.append(data)

    extra = sorted(found - expected)
    missing = sorted(expected - found)
    if extra:
        problems.append(f"extra trials: {extra}")
    if missing and not allow_incomplete:
        problems.append(f"missing trials: {missing}")
    if problems:
        raise ValueError("; ".join(problems))
    return data_rows


def _require_benchmark_isolation(manifest: dict[str, Any], allow_unsafe: bool) -> None:
    isolation = manifest.get("isolation")
    capabilities = isolation.get("capabilities") if isinstance(isolation, dict) else None
    evidence = isolation.get("evidence") if isinstance(isolation, dict) else None
    dynamic_probe = evidence.get("dynamic_probe") if isinstance(evidence, dict) else None
    required = (
        "benchmark_secrets_isolated",
        "sibling_trials_isolated",
        "candidate_isolated",
    )
    safe = (
        isinstance(isolation, dict)
        and isolation.get("requested") == "strict"
        and isolation.get("backend") == "darwin-seatbelt"
        and isolation.get("available") is True
        and isinstance(capabilities, dict)
        and all(capabilities.get(name) is True for name in required)
        and isinstance(dynamic_probe, list)
        and all(name in dynamic_probe for name in required)
    )
    if not safe and not allow_unsafe:
        raise ValueError(
            "run lacks verified strict benchmark isolation; use the explicit "
            "debug override only for non-reportable diagnostics"
        )


def aggregate_run(
    run_dir: Path,
    *,
    allow_incomplete: bool = False,
    allow_unsafe_isolation: bool = False,
) -> dict[str, Any]:
    """Verify integrity and aggregate verdicts from exactly one run directory."""
    verify_checksums(run_dir)
    manifest_path = run_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid manifest.json: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 2:
        raise ValueError("invalid manifest schema")
    _require_benchmark_isolation(manifest, allow_unsafe_isolation)
    for field in ("run_id", "created_at", "finished_at"):
        if not isinstance(manifest.get(field), str) or not manifest[field]:
            raise ValueError(f"manifest is missing finalized field: {field}")
    if manifest.get("state") != "completed" and not allow_incomplete:
        raise ValueError(f"run state is {manifest.get('state')!r}, expected 'completed'")

    data_rows = _load_and_validate_trials(run_dir, manifest, allow_incomplete)
    if manifest.get("state") == "completed" and manifest.get("trial_count") != len(data_rows):
        raise ValueError(
            f"manifest trial_count={manifest.get('trial_count')!r} does not match "
            f"validated trials={len(data_rows)}"
        )
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for data in data_rows:
        record = data["record"]
        status = data.get("status", {})
        verdict = data.get("verdict", {})
        agent_run = data.get("agent_run", {})
        key = (record["task"], record["agent"])
        rows.setdefault(
            key,
            {
                "total_trials": 0,
                "valid_attempts": 0,
                "successes": 0,
                "artifact_passes": 0,
                "infra_errors": 0,
                "modes": Counter(),
                "reasons": Counter(),
                "seconds": [],
            },
        )
        row = rows[key]
        row["total_trials"] += 1
        primary_success = record["primary_success"]
        artifact_pass = record["artifact_passed_verifier"]
        infra_error = record["infra_error"]
        trial_valid = record["trial_valid"]
        row["valid_attempts"] += int(trial_valid)
        row["successes"] += int(primary_success)
        row["artifact_passes"] += int(artifact_pass)
        row["infra_errors"] += int(infra_error)
        row["modes"].update(verdict.get("failure_modes", []))
        row["reasons"].update(record.get("status_reason", status.get("status_reason", [])))
        if agent_run.get("seconds") is not None:
            row["seconds"].append(agent_run["seconds"])

    summary: dict[str, Any] = {}
    for (task, agent), row in sorted(rows.items()):
        valid_attempts = row["valid_attempts"]
        if row["successes"] > valid_attempts:
            raise ValueError(f"successes exceed valid attempts for {(task, agent)}")
        summary.setdefault(task, {})[agent] = {
            "success_rate": row["successes"] / valid_attempts if valid_attempts else None,
            "successes": row["successes"],
            "total_trials": row["total_trials"],
            "valid_attempts": valid_attempts,
            "artifact_passes": row["artifact_passes"],
            "infra_errors": row["infra_errors"],
            "failure_modes": dict(row["modes"].most_common()),
            "status_reasons": dict(row["reasons"].most_common()),
            "avg_agent_seconds": (
                round(sum(row["seconds"]) / len(row["seconds"]), 3)
                if row["seconds"]
                else None
            ),
        }
    return summary


def markdown_table(summary: dict[str, Any]) -> str:
    lines = [
        "| Task | Agent | successes / valid | total | success rate | infra | notable modes |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for task in sorted(summary):
        for agent in sorted(summary[task]):
            stats = summary[task][agent]
            notable = stats["failure_modes"] or stats["status_reasons"]
            top = ", ".join(f"{name}×{count}" for name, count in list(notable.items())[:3])
            rate = "n/a" if stats["success_rate"] is None else f"{stats['success_rate']:.1%}"
            lines.append(
                f"| {TASK_LABEL.get(task, task)} | {agent} | "
                f"{stats['successes']} / {stats['valid_attempts']} | "
                f"{stats['total_trials']} | {rate} | {stats['infra_errors']} | {top or 'clean'} |"
            )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run-dir",
        required=True,
        type=Path,
        help="one results/runs/<run-id> directory; runs are never mixed",
    )
    parser.add_argument(
        "--allow-unsafe-isolation-debug",
        action="store_true",
        help="aggregate host/unsafe runs for debugging; such output is not reportable evidence",
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="inspect a finalized aborted/preflight run without requiring a full trial matrix",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summary = aggregate_run(
            args.run_dir.resolve(),
            allow_incomplete=args.allow_incomplete,
            allow_unsafe_isolation=args.allow_unsafe_isolation_debug,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"aggregation error: {exc}")
        return 2
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("\n" + markdown_table(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
