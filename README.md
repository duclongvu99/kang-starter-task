# Frontier coding-agent starter task

Starter-task submission prepared by Long Duc Vu for Prof. Daniel Kang. It asks
how to make a reproducible, mechanically graded measurement of where a frontier
coding agent stops succeeding under a fixed budget — and how much such a
measurement can honestly claim.

Everything reported here regenerates from committed evidence with no API access.
Jump to [Check the results](#check-the-results).

## Results

**Current round — two long-horizon Conan repository-evolution tasks.** Frozen
task snapshot, verifier and prompt; Claude Code 2.1.220 (`claude-fable-5`, ≤80
turns) and Codex CLI 0.144.6 (`gpt-5.6-sol`, high reasoning); 900 s per attempt;
benchmark-scoped macOS Seatbelt isolation.

| Task | Agent | Passing artifacts / valid trials | Invalid | Hidden-test scores |
|---|---|---:|---:|---|
| M — `conan graph explain` | Fable 5 | 0 / 5 | 0 | 2, 5, 2, 2, 2 of 10 |
| M — `conan graph explain` | GPT-5.6 Sol | 0 / 5 | 0 | 2, 4, 4, 2, 4 of 10 |
| N — platform requirements | Fable 5 | 0 / 5 | 4 quota | 29, 39, 39, 39, 39 of 41 |
| N — platform requirements | GPT-5.6 Sol | 0 / 5 | 0 | 36, 36, 36, 38, 36 of 41 |

M is the clean discriminator. N sits at the boundary, and its residual failures
land on lockfile-ordering behavior the specification underdetermines, so part of
that gap is a specification gap. **Read this as 0/5 observed under one
configuration, not as a demonstration that either model cannot do the work:**
five trials with zero passes bound the per-trial success rate below roughly 45%,
and both tasks are survivors of an adaptive search that discarded every
candidate an agent solved.

**Earlier round — nine algorithmic, concurrency and security tasks (A–I).** The
honest negative result that motivated the change of direction.

| Tasks | Outcome |
|---|---|
| A, B, D, F, G, H | Solved 5/5 by both agents |
| C | Passing artifact in all 10 trials; Fable always past the 900 s cap, so a speed limit, not a capability gap |
| E | 0/5 both — but SHA-256 preimage search hardness, which a human could not beat in budget either |
| I | 0 valid trials: both platforms refused on safety grounds. A policy boundary, not measured inability |

`REPORT.md` covers that round, including three defects found and fixed in the
harness itself.

## What is where

| Path | Contents |
|---|---|
| [`STARTER_TASK_REPORT_V2.md`](STARTER_TASK_REPORT_V2.md) | **Current report.** Result, claim limits, instrument defects, disclosure record |
| [`RESEARCH_LOG_V2.md`](RESEARCH_LOG_V2.md) | Chronology, screening funnel, per-run notes, known defects |
| [`EMAIL_TO_PROF_KANG_V2.md`](EMAIL_TO_PROF_KANG_V2.md) | Cover note |
| [`REPORT.md`](REPORT.md) | First-round (A–I) report |
| [`TASK_SPECIFICATION.md`](TASK_SPECIFICATION.md) | Admissibility protocol (12 gates) and evaluation design |
| [`tasks/`](tasks/) | Fourteen task packages. Each has an agent-visible `workspace/` and a hidden `verifier/` |
| [`evidence/runs/`](evidence/runs/) | Checksum-sealed manifests, preflight and verdicts for every reported run |
| [`harness/`](harness/) | Runner, aggregator, isolation, out-of-process graders, regression tests |

Each task package keeps the trusted reference patch and hidden regression tests
under `verifier/`, never inside the workspace the agent sees.

## Setup

Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Check the results

No agent runs or API access needed — these read the committed evidence.

```bash
# Current round: screening (k=1), confirmation (k=4), N/Fable replacements (k=4)
python harness/aggregate.py --run-dir evidence/runs/20260725T224349.182262Z-8b9db2d7
python harness/aggregate.py --run-dir evidence/runs/20260726T034819.662937Z-ae330dd8
python harness/aggregate.py --run-dir evidence/runs/20260728T062925.254874Z-d6ec0450

# Earlier round: the clean 70-trial run, the defective run kept for comparison,
# and the standalone Task H and Task I runs
python harness/aggregate.py --run-dir evidence/runs/20260725T030646.540246Z-f40db469
python harness/aggregate.py --run-dir evidence/runs/20260724T150421.630439Z-545ef5ed
python harness/aggregate.py --run-dir evidence/runs/20260725T152301.243134Z-d7bb0572
python harness/aggregate.py --run-dir evidence/runs/20260725T162204.945673Z-16ac1626
```

Expected: every row for tasks M and N reports `0 /` passes. The three current-round
bundles carry 1, 4 and 4 trials per task-agent pair respectively; in the
confirmation bundle N/fable shows `0 / 0` with `infra 4`, which is the quota
failure recorded as invalid rather than as a model failure.

Which run supplies which trial: the first valid trial of each pair comes from the
screening run; trials 2–5 come from the confirmation run, except N/Fable, whose
trials 2–5 come from the replacement run because its confirmation attempts were
quota-invalid.

The aggregator refuses to report anything unless the bundle's SHA-256 digests
and exact file set match, the manifest is `completed`, the isolation attestation
is present, and every verdict satisfies the schema. Two practical notes: each
bundle has two absolute path prefixes redacted (repository root and home
directory — the matching `…original-digests.json` holds the pre-redaction
digests and the mapping), and the file-set check is exact, so a stray `.DS_Store`
inside a bundle makes it fail with `unexpected=['.DS_Store']`.

## Check the instrument

```bash
python -m pytest -q harness/tests
```

Expected: 60 passed from inside this repository. Two of the isolation tests skip
where macOS Seatbelt is unavailable or when the suite runs outside the workspace
root, so a fresh clone elsewhere reports 58 passed, 2 skipped.

```bash
python tasks/M_conan_graph_explain/verifier/verify.py --self-test
python tasks/N_conan_platform_requires/verifier/verify.py --self-test
```

Expected: `"self_test_passed": true` with an empty `problems` list. Each self-test
applies the trusted upstream reference to a copy of the frozen snapshot and
requires it to pass every selected test (M 10/10, N 41/41), then grades the
untouched snapshot and requires it to fail (M 2/10, N 11/41). No agent result is
accepted from a task whose gate fails.

The same gate for the earlier round:

```bash
for task in A_untouchable_oracle B_sqlite_judge C_prove_it D_invariant \
            E_preimage F_concurrency G_timing_safe H_asymptotic I_exploit_chain
do
  python "tasks/${task}/verifier/verify.py" --self-test
done
```

Those self-tests additionally grade known-bad solutions and require each to fail
on its intended mode. Task E is the declared exception: no in-budget passing
reference can exist without leaking the witness, so its self-test validates the
checking logic on a throwaway instance.

## Re-run the agent experiment

Needs authenticated Claude Code and Codex CLIs, and is intentionally expensive —
each trial may take the full 900 s. Preflight runs a live tooling check first:
each agent must execute a command inside its real sandbox before any trial is
scored, and the run fails closed if one cannot.

```bash
# current round
python harness/run_all.py --tasks M,N --agents fable,sol --k 5 \
                          --budget 900 --isolation strict

# earlier round
python harness/run_all.py --tasks A,B,C,D,E,F,G --agents fable,sol --k 5 \
                          --budget 900 --isolation strict
```

Fresh runs land in `results/runs/<run-id>/` and are not committed: a full run is
hundreds of megabytes of transcripts and sandboxes. Export a sealed, redacted
bundle from one with:

```bash
python harness/export_evidence.py --source-run results/runs/<run-id>
```

Grading is unconditional, so **a passing artifact counts as a solve even if the
agent timed out or exited nonzero**. Quota failures, policy refusals, CLI crashes
and verifier infrastructure failures are recorded as invalid trials and never as
model failures.

## Limits worth knowing before reading anything else

- Five trials per pair; 0/5 bounds the true per-trial success rate below ~45%.
- M and N survived an adaptive, non-preregistered search over ~14 candidates.
- The grader treats pytest's exit code as its pass signal, so a submission that
  edited `conans/test/conftest.py` could force a false pass. No counted trial did
  — all twenty graded sandboxes were diffed — and it is disclosed rather than
  patched because editing a verifier invalidates the trials graded under it.
- Isolation is benchmark-scoped; the solving phase is not network-isolated.
- Both source PRs predate the models' training cutoffs.

`STARTER_TASK_REPORT_V2.md` §5 and §7 give the full list with evidence.
