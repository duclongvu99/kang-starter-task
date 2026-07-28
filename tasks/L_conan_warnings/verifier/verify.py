from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "harness"))
from repo_task_verifier import grade_repo_task, self_test_repo_task

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parent / "workspace"
TARGETS = [
    "conans/test/integration/remote/retry_test.py",
    "conans/test/integration/remote/broken_download_test.py",
    "conans/test/unittests/tools/files/test_patches.py",
    "conans/test/integration/command_v2/test_output.py",
]


def grade(submission):
    return grade_repo_task(submission_dir=submission, project_root=ROOT, verifier_dir=HERE,
                           task_name="L_conan_warnings", test_targets=TARGETS, timeout=180)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--submission")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test_repo_task(project_root=ROOT, verifier_dir=HERE, workspace=WORKSPACE,
                                   task_name="L_conan_warnings", test_targets=TARGETS,
                                   timeout=180)
    if not args.submission:
        parser.error("either --submission or --self-test is required")
    print(json.dumps(grade(args.submission), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
