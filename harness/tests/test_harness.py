from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from unittest import mock

import pytest

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))

import aggregate  # noqa: E402
import export_evidence  # noqa: E402
import run_all  # noqa: E402


def _args(runs_root: Path, **updates: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "tasks": "A",
        "agents": "sol",
        "k": 1,
        "budget": 2,
        "grade_timeout": 2,
        "preflight_timeout": 2,
        "concurrency": 1,
        "runs_root": str(runs_root),
    }
    values.update(updates)
    return argparse.Namespace(**values)


def _agent_metadata(*, present: bool = True) -> dict:
    return {
        "executable": "sol",
        "path": sys.executable if present else None,
        "version": "test",
        "version_returncode": 0 if present else None,
    }


def _fake_task(
    tmp_path: Path,
    *,
    self_test_exit: int = 0,
    self_test_output: str = '{"self_test_passed": true}',
) -> Path:
    task = tmp_path / "task"
    (task / "workspace").mkdir(parents=True)
    (task / "workspace" / "README.md").write_text("test", encoding="utf-8")
    (task / "verifier").mkdir()
    (task / "verifier" / "verify.py").write_text(
        "import sys\n"
        "if '--self-test' in sys.argv:\n"
        f"    print({self_test_output!r})\n"
        f"    raise SystemExit({self_test_exit})\n",
        encoding="utf-8",
    )
    return task


def _write_completed_run(
    tmp_path: Path,
    records: list[dict],
    *,
    k: int = 1,
    state: str = "completed",
) -> Path:
    run_dir = tmp_path / "run-one"
    run_dir.mkdir()
    manifest = {
        "schema_version": 2,
        "run_id": run_dir.name,
        "created_at": "2026-01-01T00:00:00Z",
        "finished_at": "2026-01-01T00:01:00Z",
        "state": state,
        "arguments": {"tasks": "A", "agents": "sol", "k": k},
        "trial_count": len(records),
        "isolation": {
            "requested": "strict",
            "backend": "darwin-seatbelt",
            "available": True,
            "capabilities": {
                "benchmark_secrets_isolated": True,
                "sibling_trials_isolated": True,
                "candidate_isolated": True,
            },
            "evidence": {
                "dynamic_probe": [
                    "benchmark_secrets_isolated",
                    "sibling_trials_isolated",
                    "candidate_isolated",
                ]
            },
        },
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    for record in records:
        primary = record.get("primary_success", False)
        artifact_pass = record.get("artifact_passed_verifier", primary)
        infra_error = record.get("infra_error", False)
        trial_valid = record.get("trial_valid", not infra_error)
        timed_out = record.get("timed_out", False)
        returncode = record.get("returncode", -15 if timed_out else 0)
        agent_completed = record.get(
            "agent_completed", not timed_out and returncode == 0
        )
        verifier_completed = record.get("verifier_completed", True)
        reasons = record.get("status_reason", ["success"] if primary else [])
        modes = record.get("failure_modes", [])
        complete_record = {
            **record,
            "agent_completed": agent_completed,
            "artifact_passed_verifier": artifact_pass,
            "verifier_completed": verifier_completed,
            "primary_success": primary,
            "infra_error": infra_error,
            "trial_valid": trial_valid,
            "status_reason": reasons,
            "passed": primary,
            "failure_modes": modes,
            "timed_out": timed_out,
            "seconds": record.get("seconds", 2.0),
            "returncode": returncode,
        }
        trial = (
            run_dir
            / "trials"
            / complete_record["task"]
            / complete_record["agent"]
            / f"trial_{complete_record['trial']}"
        )
        trial.mkdir(parents=True)
        status = {
            field: complete_record[field]
            for field in (
                "agent_completed",
                "artifact_passed_verifier",
                "verifier_completed",
                "primary_success",
                "infra_error",
                "trial_valid",
                "status_reason",
            )
        }
        payload = {
            "schema_version": 2,
            "record": complete_record,
            "status": status,
            "agent_run": {
                "seconds": complete_record["seconds"],
                "timed_out": timed_out,
                "execution_error": None,
                "returncode": returncode,
            },
            "verifier_run": {"completed": verifier_completed},
            "verdict": {"passed": artifact_pass, "failure_modes": modes},
        }
        (trial / "verdict.json").write_text(json.dumps(payload), encoding="utf-8")
    run_all.write_checksums(run_dir)
    return run_dir


def _mutate_verdict_and_reseal(run_dir: Path, mutate) -> None:
    verdict = next(run_dir.glob("trials/*/*/trial_*/verdict.json"))
    payload = json.loads(verdict.read_text(encoding="utf-8"))
    mutate(payload)
    verdict.write_text(json.dumps(payload), encoding="utf-8")
    (run_dir / "checksums.sha256").unlink()
    run_all.write_checksums(run_dir)


def test_evidence_export_redacts_paths_and_remains_aggregatable(tmp_path: Path) -> None:
    home = tmp_path / "private-home"
    repo = home / "private-repo"
    repo.mkdir(parents=True)
    run_dir = _write_completed_run(
        repo,
        [
            {
                "task": "A",
                "agent": "sol",
                "trial": 1,
                "primary_success": False,
                "artifact_passed_verifier": False,
                "infra_error": False,
                "trial_valid": True,
            }
        ],
    )
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["private_paths_for_test"] = [str(repo / "task"), str(home / ".config")]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (run_dir / "preflight.json").write_text(
        json.dumps({"repo": str(repo), "home": str(home)}), encoding="utf-8"
    )
    (run_dir / "summary.json").write_text("{}", encoding="utf-8")
    (run_dir / "checksums.sha256").unlink()
    run_all.write_checksums(run_dir)

    destination_root = tmp_path / "bundles"
    exported = export_evidence.export_bundle(run_dir, destination_root, repo, home)
    combined = b"\n".join(path.read_bytes() for path in export_evidence._selected_files(exported))
    assert str(repo).encode() not in combined
    assert str(home).encode() not in combined
    assert b"/REPO/task" in combined
    assert b"/HOME/.config" in combined
    assert (destination_root / f"{run_dir.name}.original-digests.json").is_file()
    summary = aggregate.aggregate_run(exported)
    assert summary["A"]["sol"]["valid_attempts"] == 1


def test_unique_run_directories_never_collide(tmp_path: Path) -> None:
    first = run_all.create_run_dir(tmp_path)
    second = run_all.create_run_dir(tmp_path)
    assert first != second
    assert first.is_dir() and second.is_dir()


def test_failed_preflight_blocks_all_trials_and_is_finalized(tmp_path: Path) -> None:
    task = _fake_task(tmp_path, self_test_exit=7)
    with (
        mock.patch.dict(run_all.TASK_DIRS, {"A": task}, clear=True),
        mock.patch.object(run_all, "one_trial") as trial,
        mock.patch.object(run_all, "_agent_version", return_value=_agent_metadata()),
    ):
        run_dir, exit_code = run_all.execute(_args(tmp_path / "runs"))
    assert exit_code == 2
    trial.assert_not_called()
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["state"] == "preflight_failed"
    assert manifest["preflight_failed_tasks"] == ["A"]
    assert (run_dir / "checksums.sha256").is_file()
    aggregate.verify_checksums(run_dir)


@pytest.mark.parametrize(
    "output",
    ["", "not json", '{"passed": true}', '{"self_test_passed": false}'],
)
def test_preflight_requires_true_self_test_json(tmp_path: Path, output: str) -> None:
    task = _fake_task(tmp_path, self_test_output=output)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with mock.patch.dict(run_all.TASK_DIRS, {"A": task}, clear=True):
        result = run_all.run_preflight(
            ["A"], ["sol"], run_dir, 2, {"sol": _agent_metadata()}
        )
    assert result["passed"] is False
    assert result["tasks"]["A"]["passed"] is False


def test_missing_agent_executable_blocks_trials_as_infrastructure(tmp_path: Path) -> None:
    task = _fake_task(tmp_path)
    with (
        mock.patch.dict(run_all.TASK_DIRS, {"A": task}, clear=True),
        mock.patch.object(run_all, "one_trial") as trial,
        mock.patch.object(run_all, "_agent_version", return_value=_agent_metadata(present=False)),
    ):
        run_dir, exit_code = run_all.execute(_args(tmp_path / "runs"))
    assert exit_code == 2
    trial.assert_not_called()
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["state"] == "preflight_failed"
    assert manifest["preflight_failed_agents"] == ["sol"]
    assert manifest["preflight_failure_kind"] == "infrastructure"


def test_process_log_is_not_truncated(tmp_path: Path) -> None:
    log = tmp_path / "full.log"
    expected = "x" * 25_123
    result = run_all._run_process(
        [sys.executable, "-c", f"print({expected!r}, end='')"], tmp_path, 5, log
    )
    assert result["returncode"] == 0
    assert log.read_text(encoding="utf-8") == expected


def test_process_log_overflow_is_bounded_and_classified(tmp_path: Path) -> None:
    log = tmp_path / "bounded.log"
    result = run_all._run_process(
        [sys.executable, "-c", "print('x' * 4096, end='')"],
        tmp_path,
        5,
        log,
        log_cap_bytes=127,
    )
    assert result["returncode"] == 0
    assert result["log_overflow"] is True
    assert result["log_bytes"] == 127
    assert log.stat().st_size == 127
    assert "agent_log_overflow" in run_all.classify_agent_infrastructure(result, log)


def test_agent_log_overflow_invalidates_trial(tmp_path: Path) -> None:
    task = _fake_task(tmp_path)
    run_dir = tmp_path / "run-overflow"
    run_dir.mkdir()

    def overflowing_agent(sandbox: Path, budget: int, log_path: Path) -> dict:
        return run_all._run_process(
            [sys.executable, "-c", "print('x' * 4096, end='')"],
            sandbox,
            5,
            log_path,
            log_cap_bytes=64,
        )

    verifier_meta = {"completed": True, "error": None, "seconds": 0.1}
    with (
        mock.patch.dict(run_all.TASK_DIRS, {"A": task}, clear=True),
        mock.patch.dict(run_all.AGENTS, {"sol": overflowing_agent}, clear=True),
        mock.patch.object(run_all, "grade", return_value=({"passed": True}, verifier_meta)),
    ):
        record = run_all.one_trial("A", "sol", 1, 2, 2, run_dir)
    assert record["infra_error"] is True
    assert record["trial_valid"] is False
    assert record["primary_success"] is False
    assert "agent_log_overflow" in record["status_reason"]


def test_verdict_parser_returns_outer_object_with_nested_json() -> None:
    output = 'warning\n{"passed": true, "details": {"count": 2}}\n'
    assert run_all._parse_verdict(output) == {"passed": True, "details": {"count": 2}}


def _agent_result(log_path: Path, output: str, returncode: int, timed_out: bool = False) -> dict:
    log_path.write_text(output, encoding="utf-8")
    return {
        "returncode": returncode,
        "timed_out": timed_out,
        "execution_error": None,
        "seconds": 1.0,
        "log": str(log_path),
    }


def test_timeout_without_infra_signature_is_a_valid_failed_attempt(tmp_path: Path) -> None:
    task = _fake_task(tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    def timed_out_agent(sandbox: Path, budget: int, log_path: Path) -> dict:
        return _agent_result(log_path, "ordinary partial work", -15, timed_out=True)

    verifier_meta = {"completed": True, "error": None, "seconds": 0.1}
    with (
        mock.patch.dict(run_all.TASK_DIRS, {"A": task}, clear=True),
        mock.patch.dict(run_all.AGENTS, {"sol": timed_out_agent}, clear=True),
        mock.patch.object(run_all, "grade", return_value=({"passed": True}, verifier_meta)),
    ):
        record = run_all.one_trial("A", "sol", 1, 1, 1, run_dir)
    assert record["artifact_passed_verifier"] is True
    assert record["trial_valid"] is True
    assert record["infra_error"] is False
    assert record["primary_success"] is False
    assert "agent_timeout" in record["status_reason"]


@pytest.mark.parametrize("returncode", [0, 1])
def test_session_limit_is_invalid_infrastructure_even_with_zero_exit(
    tmp_path: Path, returncode: int
) -> None:
    task = _fake_task(tmp_path)
    run_dir = tmp_path / f"run-{returncode}"
    run_dir.mkdir()

    def limited_agent(sandbox: Path, budget: int, log_path: Path) -> dict:
        return _agent_result(log_path, "You've hit your session limit", returncode)

    verifier_meta = {"completed": True, "error": None, "seconds": 0.1}
    with (
        mock.patch.dict(run_all.TASK_DIRS, {"A": task}, clear=True),
        mock.patch.dict(run_all.AGENTS, {"sol": limited_agent}, clear=True),
        mock.patch.object(run_all, "grade", return_value=({"passed": True}, verifier_meta)),
    ):
        record = run_all.one_trial("A", "sol", 1, 1, 1, run_dir)
    assert record["trial_valid"] is False
    assert record["infra_error"] is True
    assert record["primary_success"] is False
    assert "agent_infra_signature:session_limit" in record["status_reason"]


def test_ambiguous_infra_word_in_agent_prose_does_not_void_a_clean_trial(
    tmp_path: Path,
) -> None:
    """Regression test for REPORT.md defect 3.

    A trial exited 0 and was voided because the `authentication` pattern matched the word
    "unauthorized" inside prose an unrelated editor plugin had injected into the agent's
    context. Content the agent prints must not produce a verdict about the environment
    unless the harness independently observed a failure.
    """
    task = _fake_task(tmp_path)
    run_dir = tmp_path / "run-prose"
    run_dir.mkdir()
    injected = "hooks will DENY unauthorized actions\nI could not find a nonce; giving up.\n"

    def prose_agent(sandbox: Path, budget: int, log_path: Path) -> dict:
        return _agent_result(log_path, injected, 0)

    verifier_meta = {"completed": True, "error": None, "seconds": 0.1}
    with (
        mock.patch.dict(run_all.TASK_DIRS, {"A": task}, clear=True),
        mock.patch.dict(run_all.AGENTS, {"sol": prose_agent}, clear=True),
        mock.patch.object(
            run_all, "grade", return_value=({"passed": False, "failure_modes": ["honest_giveup"]}, verifier_meta)
        ),
    ):
        record = run_all.one_trial("A", "sol", 1, 1, 1, run_dir)
    assert record["infra_error"] is False
    assert record["trial_valid"] is True, "a clean exit must stay a valid attempt"
    assert not any(r.startswith("agent_infra_signature:") for r in record["status_reason"])


def test_ambiguous_infra_word_still_voids_when_harness_saw_a_failure(tmp_path: Path) -> None:
    """The same pattern must keep working when there is real corroboration."""
    task = _fake_task(tmp_path)
    run_dir = tmp_path / "run-corroborated"
    run_dir.mkdir()

    def failing_agent(sandbox: Path, budget: int, log_path: Path) -> dict:
        return _agent_result(log_path, "authentication failed\n", 1)

    verifier_meta = {"completed": True, "error": None, "seconds": 0.1}
    with (
        mock.patch.dict(run_all.TASK_DIRS, {"A": task}, clear=True),
        mock.patch.dict(run_all.AGENTS, {"sol": failing_agent}, clear=True),
        mock.patch.object(run_all, "grade", return_value=({"passed": False}, verifier_meta)),
    ):
        record = run_all.one_trial("A", "sol", 1, 1, 1, run_dir)
    assert record["infra_error"] is True
    assert "agent_infra_signature:authentication" in record["status_reason"]


def test_source_line_401_does_not_masquerade_as_http_auth_failure(tmp_path: Path) -> None:
    """A timed-out code search can print ``file.py:401:`` in an otherwise normal log."""
    log = tmp_path / "source-line.log"
    log.write_text(
        "conans/client/graph/graph_binaries.py:401: if node.binary == BINARY_BUILD\n",
        encoding="utf-8",
    )
    reasons = run_all.classify_agent_infrastructure(
        {"returncode": -15, "timed_out": True, "execution_error": None}, log
    )
    assert "agent_infra_signature:authentication" not in reasons


def test_trial_removes_private_runtime_scratch_before_evidence_sealing(tmp_path: Path) -> None:
    task = _fake_task(tmp_path)
    run_dir = tmp_path / "run-scratch"
    run_dir.mkdir()

    def scratch_agent(sandbox: Path, budget: int, log_path: Path) -> dict:
        scratch = sandbox.parent / "agent-private"
        scratch.mkdir()
        target = scratch / "target.txt"
        target.write_text("temporary", encoding="utf-8")
        (scratch / "link.txt").symlink_to(target)
        return _agent_result(log_path, "done\n", 0)

    verifier_meta = {"completed": True, "error": None, "seconds": 0.1}
    with (
        mock.patch.dict(run_all.TASK_DIRS, {"A": task}, clear=True),
        mock.patch.dict(run_all.AGENTS, {"sol": scratch_agent}, clear=True),
        mock.patch.object(run_all, "grade", return_value=({"passed": True}, verifier_meta)),
    ):
        record = run_all.one_trial("A", "sol", 1, 1, 1, run_dir)
    assert record["primary_success"] is True
    assert not (run_dir / "trials" / "A" / "sol" / "trial_1" / "agent-private").exists()


def test_platform_refusal_is_labeled_distinctly_not_as_nonzero_exit(tmp_path: Path) -> None:
    """A safety refusal is its own outcome, never a generic nonzero exit or infra failure.

    Both agents' platforms refused Task I (offensive security) with rc=1. Without this the
    refusal would be read as `agent_nonzero_exit` and be indistinguishable from a crash;
    it must surface as `agent_refused:<platform>` so it is never mistaken for incapability.
    """
    log = tmp_path / "refusal.log"
    log.write_text(
        "I'll read the spec.\n"
        "API Error: Opus 5's safeguards flagged this message "
        "(https://www.anthropic.com/legal/aup). Claude Code can't respond to this message.\n",
        encoding="utf-8",
    )
    agent_run = {"returncode": 1, "timed_out": False, "execution_error": None}
    reasons = run_all.classify_agent_infrastructure(agent_run, log)
    assert "agent_refused:claude_aup" in reasons
    assert "agent_nonzero_exit" not in reasons, "refusal must not double-count as a crash"

    codex_log = tmp_path / "codex_refusal.log"
    codex_log.write_text("ERROR: This content was flagged for possible cybersecurity risk.\n",
                         encoding="utf-8")
    codex_reasons = run_all.classify_agent_infrastructure(
        {"returncode": 1, "timed_out": False, "execution_error": None}, codex_log
    )
    assert "agent_refused:codex_cyber" in codex_reasons


def test_teardown_permission_error_does_not_become_an_execution_error() -> None:
    """Regression test for REPORT.md defect 2 (the teardown race).

    `killpg(pid, 0)` raising EPERM used to escape into the caller's OSError handler and be
    recorded as an execution error, so one 900 s timeout scored valid and the next scored
    invalid depending on which side of a race the kill landed on.
    """
    process = mock.Mock()
    process.pid = 4242
    process.poll.return_value = None
    process.wait.return_value = 0
    result: dict = {"execution_error": None, "teardown_error": None}

    def killpg(pid: int, sig: int) -> None:
        if sig == 0:
            raise PermissionError(1, "Operation not permitted")

    with mock.patch.object(run_all.os, "killpg", side_effect=killpg):
        run_all._teardown_process_group(process, result)

    assert result["execution_error"] is None
    assert result["teardown_error"] is None


def test_tool_check_failure_blocks_the_whole_preflight(tmp_path: Path) -> None:
    """Gate G12(e): a mute agent must never reach a scored trial, even if trials pass."""
    task = _fake_task(tmp_path)
    run_dir = tmp_path / "run-toolcheck"
    run_dir.mkdir()
    dead = {
        "agent": "sol",
        "passed": False,
        "observed": "BROKEN",
        "error": "agent could not execute a shell command in its sandbox",
    }
    with (
        mock.patch.dict(run_all.TASK_DIRS, {"A": task}, clear=True),
        mock.patch.object(run_all, "_agent_version", return_value=_agent_metadata()),
        mock.patch.object(run_all, "run_tool_check", return_value=dead),
    ):
        report = run_all.run_preflight(["A"], ["sol"], run_dir, 5, None, "host")
    assert report["passed"] is False
    assert report["agents"]["sol"]["passed"] is False
    assert report["agents"]["sol"]["tool_check"]["observed"] == "BROKEN"
    assert report["tool_check_skipped"] is False


def test_aggregation_excludes_invalid_infra_trials_from_denominator(tmp_path: Path) -> None:
    run_dir = _write_completed_run(
        tmp_path,
        [
            {
                "task": "A",
                "agent": "sol",
                "trial": 1,
                "primary_success": False,
                "artifact_passed_verifier": True,
                "infra_error": True,
                "trial_valid": False,
                "status_reason": ["agent_infra_signature:session_limit"],
            }
        ],
    )
    summary = aggregate.aggregate_run(run_dir)
    assert summary["A"]["sol"]["successes"] == 0
    assert summary["A"]["sol"]["total_trials"] == 1
    assert summary["A"]["sol"]["valid_attempts"] == 0
    assert summary["A"]["sol"]["success_rate"] is None
    assert summary["A"]["sol"]["artifact_passes"] == 1


def test_aggregation_fails_closed_on_incomplete_matrix(tmp_path: Path) -> None:
    run_dir = _write_completed_run(
        tmp_path,
        [
            {
                "task": "A",
                "agent": "sol",
                "trial": 1,
                "primary_success": False,
                "artifact_passed_verifier": False,
                "infra_error": False,
                "trial_valid": True,
            }
        ],
        k=2,
    )
    with pytest.raises(ValueError, match="missing trials"):
        aggregate.aggregate_run(run_dir)
    summary = aggregate.aggregate_run(run_dir, allow_incomplete=True)
    assert summary["A"]["sol"]["total_trials"] == 1


def test_aggregation_rejects_extra_trial(tmp_path: Path) -> None:
    base = {
        "task": "A",
        "agent": "sol",
        "primary_success": False,
        "artifact_passed_verifier": False,
        "infra_error": False,
        "trial_valid": True,
    }
    run_dir = _write_completed_run(
        tmp_path,
        [{**base, "trial": 1}, {**base, "trial": 2}],
        k=1,
    )
    with pytest.raises(ValueError, match="extra trials"):
        aggregate.aggregate_run(run_dir)


def test_aggregation_rejects_duplicate_or_mismatched_trial_identity(tmp_path: Path) -> None:
    run_dir = _write_completed_run(
        tmp_path,
        [
            {
                "task": "A",
                "agent": "sol",
                "trial": 1,
                "primary_success": False,
                "artifact_passed_verifier": False,
                "infra_error": False,
                "trial_valid": True,
            }
        ],
    )
    source = run_dir / "trials" / "A" / "sol" / "trial_1" / "verdict.json"
    duplicate = run_dir / "trials" / "A" / "sol" / "trial_2"
    duplicate.mkdir()
    duplicate.joinpath("verdict.json").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    # Re-seal the intentionally malformed fixture.
    (run_dir / "checksums.sha256").unlink()
    run_all.write_checksums(run_dir)
    with pytest.raises(ValueError, match="trial identity mismatch"):
        aggregate.aggregate_run(run_dir)


def test_aggregation_rejects_checksum_tampering(tmp_path: Path) -> None:
    run_dir = _write_completed_run(
        tmp_path,
        [
            {
                "task": "A",
                "agent": "sol",
                "trial": 1,
                "primary_success": False,
                "artifact_passed_verifier": False,
                "infra_error": False,
                "trial_valid": True,
            }
        ],
    )
    verdict = run_dir / "trials" / "A" / "sol" / "trial_1" / "verdict.json"
    verdict.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        aggregate.aggregate_run(run_dir)


def test_aggregation_rejects_string_boolean(tmp_path: Path) -> None:
    run_dir = _write_completed_run(
        tmp_path,
        [{"task": "A", "agent": "sol", "trial": 1, "trial_valid": True}],
    )

    def mutate(payload: dict) -> None:
        payload["record"]["primary_success"] = "false"
        payload["status"]["primary_success"] = "false"

    _mutate_verdict_and_reseal(run_dir, mutate)
    with pytest.raises(ValueError, match="actual boolean"):
        aggregate.aggregate_run(run_dir)


def test_aggregation_rejects_inconsistent_primary_success(tmp_path: Path) -> None:
    run_dir = _write_completed_run(
        tmp_path,
        [{"task": "A", "agent": "sol", "trial": 1, "trial_valid": True}],
    )

    def mutate(payload: dict) -> None:
        payload["record"]["primary_success"] = True
        payload["status"]["primary_success"] = True
        payload["record"]["passed"] = True

    _mutate_verdict_and_reseal(run_dir, mutate)
    with pytest.raises(ValueError, match="primary_success violates"):
        aggregate.aggregate_run(run_dir)


def test_replacing_sealed_file_with_symlink_is_checksum_mismatch(tmp_path: Path) -> None:
    run_dir = _write_completed_run(
        tmp_path,
        [{"task": "A", "agent": "sol", "trial": 1, "trial_valid": True}],
    )
    verdict = next(run_dir.glob("trials/*/*/trial_*/verdict.json"))
    external = tmp_path / "external.json"
    external.write_text(verdict.read_text(encoding="utf-8"), encoding="utf-8")
    verdict.unlink()
    verdict.symlink_to(external)
    external.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        aggregate.verify_checksums(run_dir)


def test_checksum_seals_symlink_without_following_external_directory(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-symlink"
    run_dir.mkdir()
    external = tmp_path / "external-dir"
    external.mkdir()
    (external / "outside.txt").write_text("before", encoding="utf-8")
    linked = run_dir / "linked"
    linked.symlink_to(external, target_is_directory=True)
    run_all.write_checksums(run_dir)
    aggregate.verify_checksums(run_dir)

    # The target is outside the evidence root and must never be followed.
    (external / "outside.txt").write_text("after", encoding="utf-8")
    aggregate.verify_checksums(run_dir)

    linked.unlink()
    other = tmp_path / "other-external-dir"
    other.mkdir()
    linked.symlink_to(other, target_is_directory=True)
    with pytest.raises(ValueError, match="checksum mismatch"):
        aggregate.verify_checksums(run_dir)


def test_successful_execute_completes_seals_and_aggregates(tmp_path: Path) -> None:
    task = _fake_task(tmp_path)

    def clean_agent(sandbox: Path, budget: int, log_path: Path) -> dict:
        return _agent_result(log_path, "completed", 0)

    verifier_meta = {"completed": True, "error": None, "seconds": 0.1}
    with (
        mock.patch.dict(run_all.TASK_DIRS, {"A": task}, clear=True),
        mock.patch.dict(run_all.AGENTS, {"sol": clean_agent}, clear=True),
        mock.patch.object(run_all, "_agent_version", return_value=_agent_metadata()),
        mock.patch.object(run_all, "grade", return_value=({"passed": True}, verifier_meta)),
    ):
        run_dir, exit_code = run_all.execute(_args(tmp_path / "runs"))
    assert exit_code == 0
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["state"] == "completed"
    assert manifest["trial_count"] == 1
    aggregate.verify_checksums(run_dir)
    with pytest.raises(ValueError, match="strict benchmark isolation"):
        aggregate.aggregate_run(run_dir)
    summary = aggregate.aggregate_run(run_dir, allow_unsafe_isolation=True)
    assert summary["A"]["sol"]["success_rate"] == 1.0
    assert summary["A"]["sol"]["valid_attempts"] == 1


def test_mocked_strict_execute_records_verified_capabilities(tmp_path: Path) -> None:
    task = _fake_task(tmp_path)

    def clean_agent(sandbox: Path, budget: int, log_path: Path) -> dict:
        return _agent_result(log_path, "completed", 0)

    strict_resolution = run_all.process_isolation.IsolationResolution(
        requested="strict",
        backend="darwin-seatbelt",
        available=True,
        capabilities={
            "benchmark_secrets_isolated": True,
            "sibling_trials_isolated": True,
            "candidate_isolated": True,
        },
        evidence={
            "dynamic_probe": [
                "benchmark_secrets_isolated",
                "sibling_trials_isolated",
                "candidate_isolated",
            ]
        },
        warning="benchmark-scoped",
    )
    verifier_meta = {"completed": True, "error": None, "seconds": 0.1}
    with (
        mock.patch.dict(run_all.TASK_DIRS, {"A": task}, clear=True),
        mock.patch.dict(run_all.AGENTS, {"sol": clean_agent}, clear=True),
        mock.patch.object(run_all, "_agent_version", return_value=_agent_metadata()),
        mock.patch.object(run_all, "grade", return_value=({"passed": True}, verifier_meta)),
        mock.patch.object(run_all.process_isolation, "probe", return_value=strict_resolution),
    ):
        run_dir, exit_code = run_all.execute(
            _args(tmp_path / "strict-runs", isolation="strict")
        )
    assert exit_code == 0
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["isolation"]["requested"] == "strict"
    assert manifest["isolation"]["capabilities"]["benchmark_secrets_isolated"] is True
    summary = aggregate.aggregate_run(run_dir)
    assert summary["A"]["sol"]["success_rate"] == 1.0


def test_cli_defaults_to_strict_isolation() -> None:
    assert run_all.parse_args([]).isolation == "strict"


def test_preflight_rejects_failed_agent_version_command(tmp_path: Path) -> None:
    task = _fake_task(tmp_path)
    run_dir = tmp_path / "version-run"
    run_dir.mkdir()
    metadata = _agent_metadata()
    metadata["version_returncode"] = 7
    with mock.patch.dict(run_all.TASK_DIRS, {"A": task}, clear=True):
        result = run_all.run_preflight(
            ["A"], ["sol"], run_dir, 2, {"sol": metadata}
        )
    assert result["passed"] is False
    assert result["agents"]["sol"]["passed"] is False
    assert "--version failed" in result["agents"]["sol"]["error"]


def test_preflight_rejects_missing_selected_workspace(tmp_path: Path) -> None:
    task = tmp_path / "missing-workspace-task"
    (task / "verifier").mkdir(parents=True)
    (task / "verifier" / "verify.py").write_text("", encoding="utf-8")
    run_dir = tmp_path / "workspace-run"
    run_dir.mkdir()
    with mock.patch.dict(run_all.TASK_DIRS, {"A": task}, clear=True):
        result = run_all.run_preflight(
            ["A"], ["sol"], run_dir, 2, {"sol": _agent_metadata()}
        )
    assert result["passed"] is False
    assert result["tasks"]["A"]["workspace_ready"] is False


def test_process_group_cleanup_always_waits_after_esrch() -> None:
    process = mock.Mock()
    process.pid = 123456
    process.wait.return_value = 0
    with mock.patch.object(run_all.os, "killpg", side_effect=ProcessLookupError):
        run_all._terminate_process_group(process)
    process.wait.assert_called_once_with(timeout=2)


def test_unexpected_trial_exception_aborts_and_finalizes_run(tmp_path: Path) -> None:
    task = _fake_task(tmp_path)
    with (
        mock.patch.dict(run_all.TASK_DIRS, {"A": task}, clear=True),
        mock.patch.object(run_all, "_agent_version", return_value=_agent_metadata()),
        # The G12(e) tooling check spawns the real agent CLI; this test is about trial
        # exception handling, so stub it rather than making a live call.
        mock.patch.object(
            run_all,
            "run_tool_check",
            return_value={"agent": "sol", "passed": True, "observed": "TOOLCHECK_OK", "error": None},
        ),
        mock.patch.object(run_all, "one_trial", side_effect=RuntimeError("boom")),
    ):
        run_dir, exit_code = run_all.execute(_args(tmp_path / "runs"))
    assert exit_code == 3
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["state"] == "aborted"
    assert manifest["error"]["type"] == "RuntimeError"
    assert (run_dir / "error.json").is_file()
    aggregate.verify_checksums(run_dir)


@pytest.mark.parametrize(
    "updates",
    [
        {"tasks": ""},
        {"tasks": "A,A"},
        {"agents": "sol,"},
        {"agents": "sol,sol"},
        {"budget": 0},
        {"grade_timeout": 0},
        {"preflight_timeout": 0},
    ],
)
def test_invalid_cli_matrix_is_rejected_before_run(tmp_path: Path, updates: dict) -> None:
    with pytest.raises(ValueError):
        run_all.execute(_args(tmp_path / "runs", **updates))
    assert not (tmp_path / "runs").exists()
