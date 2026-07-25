# Frontier coding-agent starter task

This repository contains the starter-task submission prepared by Long Duc Vu for
Prof. Daniel Kang. It studies how to make a reproducible, mechanically graded claim
that a frontier coding agent cannot complete a task under a fixed budget.

**Headline result:** across seven tasks and one 70-trial run (Claude Fable via Claude Code vs
GPT-5.6 Sol via Codex, k=5, 900 s each), **six of the seven were solved by both agents.** The
seventh is a SHA-256 preimage — search hardness, not a capability gap, and a declared exception
to this suite's own admissibility gates. Two of the seven tasks were built *specifically* to
find a capability gap, after the first five failed to; both were solved. The honest negative
result, and the evidence that makes it checkable, is the submission.

**The finding I did not plan:** reading all 70 transcripts revealed that the harness's own sandbox
had disabled Claude Fable's shell in 22 of its 35 trials — it could not run the visible tests, a
solver, or any command at all — and it produced a verifier-passing artifact in **every one of
those 22**. That is the strongest evidence here that these tasks fall to reasoning rather than
iteration, and simultaneously a validity defect in my own harness. Both are written up in
`REPORT.md` under "Three defects in my own harness."

## Start here

- [`REPORT.md`](REPORT.md) — the short report: results, the Task E reward-hacking finding, two
  defects found in the harness's own trial classifier, where the published gaps actually are,
  and the task I would build next.
- [`TASK_SPECIFICATION.md`](TASK_SPECIFICATION.md) — the admissibility protocol (12 gates) and
  evaluation design.
- [`evidence/runs/`](evidence/runs/) — the committed provenance for the reported run: manifest,
  preflight (grader-validity gates), and all 70 trial verdicts, with the run's original SHA-256
  digests. Every number in the report regenerates from this directory.
- [`evidence/`](evidence/) — the original in-process verifier, the observed frame-introspection
  exploit against it, and an honest search attempt.
- [`tasks/`](tasks/) — seven task workspaces with hidden mechanical verifiers and
  reference/known-bad implementations. F (concurrency correctness, graded by an exhaustive
  interleaving model checker) and G (timing-safe comparison, graded by a deterministic
  opcode/AST leak detector) were added after an audit to hunt for a capability gap; both models
  solved both.
- [`harness/`](harness/) — isolated execution, aggregation, and regression tests.

## Setup

Python 3.11 or newer is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Reproduce the reported numbers

No agent runs or API access needed — this reads the committed evidence:

```bash
python harness/aggregate.py --run-dir evidence/runs/20260724T150421.630439Z-545ef5ed
```

The aggregator verifies the bundle's SHA-256 digests and the run's isolation attestation before
it will report anything, and refuses runs that are incomplete or not strictly isolated. Two
practical notes: the bundle has two absolute path prefixes redacted (repository root and home
directory — see `…545ef5ed.original-digests.json` for the pre-redaction digests and the exact
mapping), and the digest check is exact about the file set, so a stray `.DS_Store` inside the
bundle directory will make it fail with `unexpected=['.DS_Store']`.

## Validate the harness and verifiers

```bash
python -m pytest -q harness/tests        # 52 tests

for task in \
  A_untouchable_oracle \
  B_sqlite_judge \
  C_prove_it \
  D_invariant \
  E_preimage \
  F_concurrency \
  G_timing_safe
do
  python "tasks/${task}/verifier/verify.py" --self-test
done
```

Each self-test validates its oracle on known ground truth, grades a correct reference solution
and asserts it passes, grades known-bad solutions and asserts each fails on its intended mode,
and confirms a trivial baseline fails. No agent result is accepted from a task whose gate fails.
(Task E is the declared exception: no in-budget passing reference can exist without leaking the
witness, so its self-test validates the *checking logic* on a throwaway instance — see
`REPORT.md`.)

## Re-run the agent experiment

Needs authenticated Claude Code and Codex CLIs. A complete run is intentionally expensive:
seven tasks × two agents × five trials, up to 900 s each (~7 h wall clock).

```bash
python harness/run_all.py \
  --tasks A,B,C,D,E,F,G \
  --agents fable,sol \
  --k 5 \
  --budget 900 \
  --isolation strict
```

Fresh runs are written to `results/runs/<run-id>/` and are not committed: the full directory for
the reported run is 281 MB of agent transcripts and 70 sandboxes, containing machine-specific
paths and execution metadata. The committed `evidence/runs/` bundle carries the manifest,
preflight and all 70 verdicts from that same run, with digests unchanged, which is what the
aggregator needs.
