# Frontier coding-agent starter task

This repository contains the starter-task submission prepared by Long Duc Vu for
Prof. Daniel Kang. It studies how to make a reproducible, mechanically graded
measurement of where a frontier coding agent stops succeeding under a fixed
budget — and how much such a measurement can honestly claim.

## July 28 second-round update

The current result is in [`STARTER_TASK_REPORT_V2.md`](STARTER_TASK_REPORT_V2.md).
After the original A–I search below, a second search packaged two long-horizon
Conan repository-evolution tasks:

- **M — `conan graph explain`:** 0/5 passing artifacts from each agent in five
  valid trials under the frozen 900-second configuration. Artifacts plateaued at
  2–5 of 10 hidden tests; this is the clean discriminator.
- **N — platform requirements:** 0/5 from each agent. Artifacts came close —
  Fable 39/41 in each of its four final trials, Sol 38/41 at best — and the
  residual failures sit on lockfile-ordering behavior the specification
  underdetermines, so part of this gap is a specification gap. Four earlier
  Fable attempts were invalid because the CLI account exhausted usage credits
  and remain disclosed separately.

Read that as **two tasks with 0/5 observed under one configuration**, not as a
demonstration that either model cannot do them: five trials with zero passes
bound the per-trial success rate below roughly 45%, and both tasks are survivors
of an adaptive search that discarded every candidate an agent solved. The report
also discloses two defects in the instrument itself (a grader tamper surface no
counted trial exercised, and a Task M verifier narrower than its own spec). The
email draft is [`EMAIL_TO_PROF_KANG_V2.md`](EMAIL_TO_PROF_KANG_V2.md), and the
experiment chronology is [`RESEARCH_LOG_V2.md`](RESEARCH_LOG_V2.md).

The two new checksum-sealed evidence bundles reproduce independently:

```bash
python harness/aggregate.py --run-dir evidence/runs/20260725T224349.182262Z-8b9db2d7
python harness/aggregate.py --run-dir evidence/runs/20260726T034819.662937Z-ae330dd8
python harness/aggregate.py --run-dir evidence/runs/20260728T062925.254874Z-d6ec0450
```

The remainder of this README describes the earlier A–I round and is retained as
part of the full-disclosure record.

**Headline result:** across seven tasks and a 70-trial run (Claude Fable via Claude Code vs GPT-5.6
Sol via Codex, k=5, 900 s each, **all 70 trials valid**), **six of the seven were solved by both
agents.** The seventh is a SHA-256 preimage — search hardness, not a capability gap, and a declared
exception to this suite's own admissibility gates. Two of the seven tasks were built *specifically*
to find a capability gap, after the first five failed to; both were solved. The honest negative
result, and the evidence that makes it checkable, is the submission.

Two further tasks were added afterward (their own runs): **H** (asymptotic scale-blindness) — solved
10/10, a third purpose-built gap hunt defeated — and **I** (offensive-security exploit chaining), the
one task neither agent completes, because **both platforms refuse it on safety grounds** rather than
for lack of capability. See `REPORT.md`, "Two more gap hunts."

**The finding I did not plan:** auditing all 70 transcripts of an earlier run revealed that the
harness's own sandbox had disabled Claude Fable's shell in every one of its trials that left a readable transcript — 26 of 26 — it could not run the
visible tests, a solver, or any command at all — and it produced a verifier-passing artifact in
**every one of those 26**. That is the strongest evidence here that these tasks fall to reasoning
rather than iteration, and simultaneously a validity defect in my own harness. I fixed it and re-ran
everything: dead-shell signatures went from 26 of 26 readable transcripts to 0 of 27, the affected agent got 51–67% faster on
four tasks, and the unaffected agent did not move. Both runs are committed so the comparison is
checkable. Written up in `REPORT.md` under "Three defects in my own harness."

## Start here

- [`REPORT.md`](REPORT.md) — the short report: results, the Task E reward-hacking finding, three
  defects found and fixed in my own harness, where the published gaps actually are, and the three
  pre-registered tasks I would build next.
- [`TASK_SPECIFICATION.md`](TASK_SPECIFICATION.md) — the admissibility protocol (12 gates) and
  evaluation design.
- [`evidence/runs/`](evidence/runs/) — committed provenance for every run: the two main runs (all 70
  verdicts each) plus the standalone Task H and Task I runs. Every number in the report regenerates
  from these directories.
- [`evidence/`](evidence/) — the original in-process verifier, the observed frame-introspection
  exploit against it, and an honest search attempt.
- [`tasks/`](tasks/) — nine task workspaces with hidden mechanical verifiers and reference/known-bad
  implementations. A–E are the first pass; F (concurrency), G (timing-safe comparison), and H
  (asymptotic scale) were built to hunt for a capability gap and all three were solved; I
  (exploit chaining) is the offensive-security task both agents refuse on policy grounds.
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
# the reported clean run (7 tasks A-G)
python harness/aggregate.py --run-dir evidence/runs/20260725T030646.540246Z-f40db469

# the earlier defective run, retained so the before/after comparison is checkable
python harness/aggregate.py --run-dir evidence/runs/20260724T150421.630439Z-545ef5ed

# the two follow-up tasks (own runs): H (scale, solved) and I (exploit chain, refused)
python harness/aggregate.py --run-dir evidence/runs/20260725T152301.243134Z-d7bb0572
python harness/aggregate.py --run-dir evidence/runs/20260725T162204.945673Z-16ac1626
```

The aggregator verifies each bundle's SHA-256 digests and the run's isolation attestation before it
will report anything, and refuses runs that are incomplete or not strictly isolated. Two practical
notes: each bundle has two absolute path prefixes redacted (repository root and home directory — see
the matching `…original-digests.json` for the pre-redaction digests and the exact mapping), and the
digest check is exact about the file set, so a stray `.DS_Store` inside a bundle directory will make
it fail with `unexpected=['.DS_Store']`.

## Validate the harness and verifiers

```bash
python -m pytest -q harness/tests        # 60 tests; isolation tests skip
                                         # where macOS Seatbelt is unavailable

for task in \
  A_untouchable_oracle \
  B_sqlite_judge \
  C_prove_it \
  D_invariant \
  E_preimage \
  F_concurrency \
  G_timing_safe \
  H_asymptotic \
  I_exploit_chain
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
seven tasks × two agents × five trials, up to 900 s each (~6 h wall clock). Preflight
runs a live tooling check first (gate G12(e)): each agent must execute a command inside
its real sandbox before any trial is scored, and the run fails closed if one cannot.

```bash
python harness/run_all.py \
  --tasks A,B,C,D,E,F,G \
  --agents fable,sol \
  --k 5 \
  --budget 900 \
  --isolation strict
```

Fresh runs are written to `results/runs/<run-id>/` and are not committed: each full run directory is
hundreds of megabytes of agent transcripts and 70 sandboxes. The committed `evidence/runs/` bundles
carry the manifest, preflight and all 70 verdicts from each run — which is all the aggregator needs —
with two path prefixes redacted and the pre-redaction digests published alongside.
