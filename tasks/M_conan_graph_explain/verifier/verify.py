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
    "conans/test/integration/command_v2/test_graph_find_binaries.py",
    "conans/test/functional/only_source_test.py::OnlySourceTest::test_build_policies_in_conanfile",
    "conans/test/integration/command/install/install_missing_dep_test.py",
]


def grade(submission):
    return grade_repo_task(submission_dir=submission, project_root=ROOT, verifier_dir=HERE,
                           task_name="M_conan_graph_explain", test_targets=TARGETS, timeout=180)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--submission")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test_repo_task(project_root=ROOT, verifier_dir=HERE, workspace=WORKSPACE,
                                   task_name="M_conan_graph_explain", test_targets=TARGETS,
                                   timeout=180)
    if not args.submission:
        parser.error("either --submission or --self-test is required")
    print(json.dumps(grade(args.submission), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

