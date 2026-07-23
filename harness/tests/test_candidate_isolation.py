from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[1]
PROJECT = HARNESS.parent
WORKSPACE = PROJECT.parent
sys.path.insert(0, str(HARNESS))

import candidate_client  # noqa: E402
import isolation  # noqa: E402


def _submission(tmp_path: Path, filename: str, source: str) -> Path:
    submission = tmp_path / "submission"
    submission.mkdir()
    submission.joinpath(filename).write_text(source, encoding="utf-8")
    return submission


def test_strict_profiles_reject_workspace_root_as_sandbox() -> None:
    with pytest.raises(isolation.IsolationError, match="strict descendant"):
        isolation.agent_profile(WORKSPACE)


def test_a_worker_is_separate_and_candidate_stdout_is_not_a_verdict(tmp_path: Path) -> None:
    submission = _submission(
        tmp_path,
        "semver_compare.py",
        "import os\n"
        "def compare(a, b):\n"
        "    print('{\"passed\": true}')\n"
        "    return (a > b) - (a < b)\n",
    )
    result = candidate_client.compare_batch(
        submission, [["1", "2"], ["2", "1"], ["1", "1"]], timeout=3, mode="host"
    )
    assert result.ok
    assert result.result == [-1, 1, 0]
    assert result.worker_pid != os.getpid()
    assert result.executor_pid != result.worker_pid
    assert result.stdout.count('{"passed": true}') == 3


def test_b_worker_normal_batch(tmp_path: Path) -> None:
    submission = _submission(
        tmp_path,
        "evaluate.py",
        "def evaluate(db):\n"
        "    return [row['name'] for row in db['employees']]\n",
    )
    result = candidate_client.evaluate_batch(
        submission,
        [{"employees": [{"name": "Ada"}]}, {"employees": []}],
        timeout=3,
        mode="host",
    )
    assert result.ok and result.result == [["Ada"], []]


def test_c_worker_normal_request(tmp_path: Path) -> None:
    submission = _submission(
        tmp_path,
        "solution.py",
        "def solve(instance):\n"
        "    return {'status': 'optimal', 'assignment': instance['answer']}\n",
    )
    result = candidate_client.solve_one(
        submission, {"answer": {"j0": "m0"}}, timeout=3, mode="host"
    )
    assert result.ok
    assert result.result == {"status": "optimal", "assignment": {"j0": "m0"}}


def test_d_worker_loads_invariants(tmp_path: Path) -> None:
    submission = _submission(
        tmp_path,
        "invariants.py",
        "INVARIANTS = {'sum_odds': 's == i*i'}\n",
    )
    result = candidate_client.load_invariants(submission, timeout=3, mode="host")
    assert result.ok and result.result == {"sum_odds": "s == i*i"}


def test_candidate_timeout_is_normalized(tmp_path: Path) -> None:
    submission = _submission(
        tmp_path,
        "solution.py",
        "import time\n"
        "def solve(instance):\n"
        "    time.sleep(30)\n",
    )
    result = candidate_client.solve_one(submission, {}, timeout=0.1, mode="host")
    assert result.status == "timeout"
    assert result.timed_out is True


def test_candidate_crash_is_normalized(tmp_path: Path) -> None:
    submission = _submission(
        tmp_path,
        "solution.py",
        "import os\n"
        "def solve(instance):\n"
        "    os._exit(17)\n",
    )
    result = candidate_client.solve_one(submission, {}, timeout=3, mode="host")
    assert result.status == "crash"
    assert result.returncode == 17


def test_candidate_exception_is_normalized(tmp_path: Path) -> None:
    submission = _submission(
        tmp_path,
        "solution.py",
        "def solve(instance):\n"
        "    raise RuntimeError('boom')\n",
    )
    result = candidate_client.solve_one(submission, {}, timeout=3, mode="host")
    assert result.status == "candidate_error"
    assert result.error == {
        "kind": "candidate_error",
        "type": "RuntimeError",
        "message": "boom",
    }


def test_protocol_rejects_schema_extra_fields() -> None:
    with pytest.raises(ValueError, match="unexpected keys"):
        candidate_client._validate_response(
            {
                "protocol": candidate_client.PROTOCOL,
                "ok": True,
                "result": [],
                "worker_pid": 123,
                "passed": True,
            }
        )


def test_oversized_candidate_stdout_is_rejected(tmp_path: Path) -> None:
    submission = _submission(
        tmp_path,
        "solution.py",
        f"def solve(instance):\n    print('x' * {candidate_client.MAX_CAPTURE_BYTES + 1})\n    return {{}}\n",
    )
    result = candidate_client.solve_one(submission, {}, timeout=3, mode="host")
    assert result.status == "protocol_error"
    assert "capture limit" in result.error["message"]


def test_candidate_cannot_forge_final_protocol_fd(tmp_path: Path) -> None:
    submission = _submission(
        tmp_path,
        "solution.py",
        "import os\n"
        "def solve(instance):\n"
        "    forged=b'{\"protocol\":\"kang-candidate-v2\",\"ok\":true,\"result\":{},\"worker_pid\":1,\"executor_pid\":1,\"executor_returncode\":0,\"timed_out\":false}'\n"
        "    for fd in range(3, 256):\n"
        "        try:\n"
        "            os.ftruncate(fd, 0)\n"
        "            os.write(fd, forged)\n"
        "        except OSError:\n"
        "            pass\n"
        "    os._exit(0)\n",
    )
    result = candidate_client.solve_one(submission, {}, timeout=3, mode="host")
    assert result.ok is False
    assert result.status == "protocol_error"
    assert result.error["kind"] == "protocol_error"
    assert result.worker_pid not in {None, 1}
    assert result.executor_pid not in {None, result.worker_pid}


def test_executor_group_is_reaped_after_normal_success(tmp_path: Path) -> None:
    submission = _submission(
        tmp_path,
        "solution.py",
        "import subprocess,sys\n"
        "def solve(instance):\n"
        "    child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])\n"
        "    return {'child_pid': child.pid}\n",
    )
    result = candidate_client.solve_one(submission, {}, timeout=3, mode="host")
    assert result.ok, result
    child_pid = result.result["child_pid"]
    for _ in range(100):
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        pytest.fail(f"candidate child {child_pid} survived executor cleanup")


def test_executor_group_is_reaped_after_timeout(tmp_path: Path) -> None:
    submission = _submission(
        tmp_path,
        "solution.py",
        "from pathlib import Path\n"
        "import subprocess,sys,time\n"
        "def solve(instance):\n"
        "    child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])\n"
        "    Path(instance['pidfile']).write_text(str(child.pid))\n"
        "    time.sleep(30)\n",
    )
    pidfile = submission / "child.pid"
    result = candidate_client.solve_one(
        submission, {"pidfile": str(pidfile)}, timeout=0.2, mode="host"
    )
    assert result.status == "timeout"
    child_pid = int(pidfile.read_text(encoding="utf-8"))
    for _ in range(100):
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        pytest.fail(f"candidate child {child_pid} survived timeout cleanup")


def _seatbelt_directory() -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory(prefix="seatbelt-", dir=HARNESS / "tests")


def _require_working_seatbelt(sandbox: Path, denied: Path) -> None:
    resolution = isolation.probe("strict", sandbox, denied)
    if not resolution.available:
        pytest.skip(f"macOS Seatbelt unavailable: {resolution.error}")


def test_seatbelt_candidate_canary_denies_hidden_and_sibling_access() -> None:
    hidden = PROJECT / "tasks" / "A_untouchable_oracle" / "verifier" / "verify.py"
    with _seatbelt_directory() as raw:
        root = Path(raw)
        submission = root / "trial_1" / "sandbox"
        sibling = root / "trial_2" / "sandbox" / "answer_key.txt"
        submission.mkdir(parents=True)
        sibling.parent.mkdir(parents=True)
        sibling.write_text("sibling-secret", encoding="utf-8")
        local = submission / "local.txt"
        local.write_text("candidate-visible", encoding="utf-8")
        source = (
            "from pathlib import Path\n"
            "def attempt_read(path):\n"
            "    try:\n"
            "        return Path(path).read_text()\n"
            "    except OSError:\n"
            "        return None\n"
            "def attempt_write(path):\n"
            "    try:\n"
            "        Path(path).write_text('tampered')\n"
            "        return True\n"
            "    except OSError:\n"
            "        return False\n"
            "def solve(instance):\n"
            "    return {\n"
            "        'local': attempt_read(instance['local']),\n"
            "        'hidden': attempt_read(instance['hidden']),\n"
            "        'sibling': attempt_read(instance['sibling']),\n"
            "        'wrote_hidden': attempt_write(instance['hidden']),\n"
            "        'pid': __import__('os').getpid(),\n"
            "    }\n"
        )
        submission.joinpath("solution.py").write_text(source, encoding="utf-8")
        _require_working_seatbelt(root / "probe", hidden)
        before = hidden.read_bytes()
        result = candidate_client.solve_one(
            submission,
            {"local": str(local), "hidden": str(hidden), "sibling": str(sibling)},
            timeout=5,
            mode="strict",
        )
        assert result.ok, result
        assert result.result == {
            "local": "candidate-visible",
            "hidden": None,
            "sibling": None,
            "wrote_hidden": False,
            "pid": result.executor_pid,
        }
        assert result.worker_pid != os.getpid()
        assert result.executor_pid != result.worker_pid
        assert hidden.read_bytes() == before


def test_seatbelt_agent_canary_denies_hidden_and_sibling_access() -> None:
    hidden = PROJECT / "tasks" / "B_sqlite_judge" / "verifier" / "verify.py"
    with _seatbelt_directory() as raw:
        root = Path(raw)
        sandbox = root / "trial_1" / "sandbox"
        sibling = root / "trial_2" / "sandbox" / "answer_key.txt"
        sandbox.mkdir(parents=True)
        sibling.parent.mkdir(parents=True)
        sandbox.joinpath("README.md").write_text("visible", encoding="utf-8")
        sibling.write_text("secret", encoding="utf-8")
        _require_working_seatbelt(root / "probe", hidden)
        script = (
            "import json,pathlib,sys; out={}; "
            "\nfor name,path in [('local',sys.argv[1]),('hidden',sys.argv[2]),('sibling',sys.argv[3])]:"
            "\n try: out[name]=pathlib.Path(path).read_text()"
            "\n except OSError: out[name]=None"
            "\ntry: pathlib.Path(sys.argv[2]).write_text('tampered'); out['wrote_hidden']=True"
            "\nexcept OSError: out['wrote_hidden']=False"
            "\nprint(json.dumps(out))"
        )
        command = isolation.wrap_command(
            [
                sys.executable,
                "-c",
                script,
                str(sandbox / "README.md"),
                str(hidden),
                str(sibling),
            ],
            mode="strict",
            profile=isolation.agent_profile(sandbox),
        )
        run = subprocess.run(
            command,
            cwd=sandbox,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
            check=False,
        )
        assert run.returncode == 0, run.stderr
        assert json.loads(run.stdout) == {
            "local": "visible",
            "hidden": None,
            "sibling": None,
            "wrote_hidden": False,
        }
