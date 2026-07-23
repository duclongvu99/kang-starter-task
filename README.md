# Frontier coding-agent starter task

This repository contains the starter-task submission prepared by Long Duc Vu for
Prof. Daniel Kang. It studies how to make a reproducible, mechanically graded claim
that a frontier coding agent cannot complete a task under a fixed budget.

## Start here

- [`REPORT.md`](REPORT.md) — short report, results, limitations, and the central
  reward-hacking finding.
- [`TASK_SPECIFICATION.md`](TASK_SPECIFICATION.md) — the admissibility protocol and
  evaluation design.
- [`evidence/`](evidence/) — the original in-process verifier, the observed
  frame-introspection exploit, and an honest search attempt.
- [`tasks/`](tasks/) — five task workspaces with hidden mechanical verifiers and
  reference/known-bad implementations.
- [`harness/`](harness/) — isolated execution, aggregation, and regression tests.

## Setup

Python 3.11 or newer is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Validate the harness and verifiers

```bash
python -m pytest -q harness/tests

for task in \
  A_untouchable_oracle \
  B_sqlite_judge \
  C_prove_it \
  D_invariant \
  E_preimage
do
  python "tasks/${task}/verifier/verify.py" --self-test
done
```

Each verifier self-test checks its oracle/reference solution, known-bad solutions,
and a trivial baseline before any agent result is accepted.

## Reproduce agent runs

The harness expects authenticated installations of the relevant Claude Code and Codex
CLIs. A complete run is intentionally expensive: five tasks, two agents, five trials,
and up to 900 seconds per trial.

```bash
python harness/run_all.py \
  --tasks A,B,C,D,E \
  --agents fable,sol \
  --k 5 \
  --budget 900

python harness/aggregate.py
```

Generated runs are written under `results/` and are not committed because raw agent
transcripts contain machine-specific paths and execution metadata. The report contains
the audited result table, and the key Task E behaviors are preserved in `evidence/`.
