# Making "a frontier coding agent cannot do this" a falsifiable claim

**Long Duc Vu** · starter task for Prof. Daniel Kang · experiments 19–28 July 2026

The instruction was to design a task specification, build two or three tasks that
Fable (Claude Code) and GPT-5.6 Sol (Codex) cannot do, and report why and how. The
hard part was never finding a task an agent fails once — stochastic single
failures are cheap and prove nothing. It was making *cannot* a claim that survives
the scrutiny your gold-label work applies to existing benchmarks.

So the deliverable is a protocol first and two tasks second. Under a frozen
configuration, **both agents produced zero passing artifacts in five valid trials
on each of two long-horizon repository-evolution tasks**, from checksum-sealed
evidence that regenerates with one command. I state that as a
configuration-bound observation rather than an impossibility claim, and §5
explains where the result is weaker than the headline suggests. This document is
self-contained; [`REPORT.md`](REPORT.md) holds the longer record.

## 1. What makes the claim hard

A task can be beyond an agent for two very different reasons, and a specification
has to say which it targets:

- **A capability gap** — a competent engineer can do it, the agent cannot. This
  reveals a limit of the *model*, and is the interesting kind.
- **Irreducible difficulty** — nobody can do it in budget (inverting a hash).
  This reveals a limit of *computation*, not the model.

That distinction disqualified my most tempting early result, and it is the reason
a SHA-256 preimage task on which both agents scored 0/5 is reported below as
inadmissible rather than as a finding.

A second problem is self-verification. If an agent can reconstruct the checker, it
can iterate to any checkable answer, and the task measures persistence rather than
reasoning. So every task here separates what the agent can see from what decides
it.

## 2. Method

**Design principle — shape vs. substance.** Every task exposes the agent to a
*weak, visible* signal it may run and iterate against, and is decided by a
*strong, hidden*, mechanically-grounded verifier it never sees. A task is
interesting precisely when an agent can make the visible signal green while the
hidden verifier still fails it.

**Admissibility gates.** A task enters the suite only if it passes all twelve.

| Gate | Requirement |
|---|---|
| G1 | Two-tier signal: weak visible checks, strong hidden decider |
| G2 | The decider is mechanical — SMT solver, model checker, differential oracle, or upstream regression suite. Never an LLM judge |
| G3 | Grader-validity gate, run before any agent: a correct reference must pass, known-bad solutions must each fail on their intended mode, a trivial baseline must fail |
| G4 | Fairness: the specification is complete enough for a competent engineer to implement |
| G5 | Disclosed rules, no undisclosed traps |
| G6 | Anti-cheat by construction: oracle, gold answers and reference unreachable from the candidate workspace |
| G7 | Resampling: "cannot" asserted only across k ≥ 5 independent trials |
| G8 | Non-discrimination sanity: if a degenerate baseline passes the hidden verifier, the task is void |
| G9 | Reproducibility: model slugs, tool versions, budgets and hashes recorded; results regenerate from committed evidence |
| G10 | Failure-mode logging: record *how* each attempt failed |
| G11 | Budgeted, dated claim, scoped to the configuration |
| G12 | Trial-validity classification is itself evidence and must be audited — including a live tool-use check inside each agent's real sandbox before any trial is scored |

**How a trial is counted.** Each attempt gets a fresh sandbox, a 900-second wall
clock, and no access to sibling trials or the verifier. Grading then runs
unconditionally and out of process, so **a passing artifact counts as a solve even
if the agent timed out or exited nonzero.** Quota failures, policy refusals, CLI
crashes and verifier infrastructure failures are recorded as *invalid* trials and
never as model failures. Completed runs are sealed with SHA-256 after every
verdict is written.

## 3. The two tasks

Both are frozen pre-change snapshots of the MIT-licensed Conan C/C++ package
manager, packaged from changes its maintainers had already shipped upstream. Each
package holds an agent-visible `SPEC.md`, a trusted upstream reference patch and
hidden regression tests (both only under `verifier/`, never in the workspace), and
the G3 self-test gate.

**M — implement `conan graph explain`.** Reconstruct a dependency graph, select a
missing binary, search the local cache and every enabled remote, rank candidates
by a lexicographic distance over platform/settings/options/dependencies, return
all candidates tied at the best distance, and keep the API, JSON, text and
existing missing-binary behavior coherent. Reference: 4 production files,
+255/−32. Hidden tests: 3 files, +207/−4 → 10 tests. Untouched baseline scores
2/10; the upstream reference scores 10/10. Base commit `f0a1b35f`, from public
[Conan PR #14694](https://github.com/conan-io/conan/pull/14694).

**N — generalize system tools into platform requirements.** Add
`[platform_requires]` and `[platform_tool_requires]`, deprecate `[system_tools]`
as an alias, and keep the new `Platform` status coherent across profile
composition, exact/range/revision resolution, host/build separation, lockfiles,
package-ID modes, generator visibility, metadata and API serialization.
Reference: 9 production files, +63/−48. Hidden tests: 4 files, +262/−39 → 41
tests. Baseline scores 11/41; the reference scores 41/41. Base commit
`3f3fd457`, from public
[Conan PR #14871](https://github.com/conan-io/conan/pull/14871).

I did not invent these features. The contribution is the packaging and the
measurement: converting real upstream changes into frozen self-contained
specifications, separating reference and hidden tests from the workspace,
building the verifier and its negative controls, and running the evaluation.

## 4. Results

Claude Code 2.1.220 (`claude-fable-5`, ≤80 turns); Codex CLI 0.144.6
(`gpt-5.6-sol`, high reasoning); 900 s per attempt; concurrency 2;
benchmark-scoped macOS Seatbelt isolation; frozen task, verifier and prompt with
hashes in every manifest.

| Task | Agent | Passing artifacts / valid trials | Invalid | Hidden-test scores |
|---|---|---:|---:|---|
| M | Fable 5 | **0 / 5** | 0 | 2, 5, 2, 2, 2 of 10 |
| M | GPT-5.6 Sol | **0 / 5** | 0 | 2, 4, 4, 2, 4 of 10 |
| N | Fable 5 | **0 / 5** | 4 quota | 29, 39, 39, 39, 39 of 41 |
| N | GPT-5.6 Sol | **0 / 5** | 0 | 36, 36, 36, 38, 36 of 41 |

The failures are partial implementations, not stalls. Every counted Fable trial
ended at the wall clock — "ran out of budget with incomplete work" — while Sol
usually exited cleanly and was wrong; I report those as distinct failure modes
rather than merging them. Four Fable attempts on N hit exhausted account credits
and are retained in the evidence as invalid, not as model failures.

The claim I will defend is exactly this:

> Under the named model/CLI versions, common prompt, frozen task and verifier,
> benchmark-scoped isolation, and 900-second budget, each agent produced zero
> passing artifacts in five valid independent trials.

## 5. Where this result is weak

**Task M is the clean result.** Both agents plateaued far from passing across five
independent trials each.

**Task N is a narrow miss on partly underdetermined behavior.** Fable's four final
artifacts each passed 39 of 41 and failed *the same two tests*. Both hinge on
resolving platform requirements *before* consulting the graph lock, reversing the
pre-existing order. My `SPEC.md` says only that lockfiles "record resolved
platform versions and enforce them on replay" — while the workspace's *visible,
non-editable* legacy test asserts the **opposite** precedence. Four independent
trials all took the legacy reading. That is evidence about my specification as
much as about the model.

**Statistical strength.** Five trials with zero passes bound the true per-trial
success rate below roughly **45%** (95% Clopper–Pearson) — far from
impossibility. Trials are procedurally independent, but neither CLI exposes a
random seed, so this is not proven statistical independence.

**Selection.** M and N are the two survivors of an adaptive, non-preregistered
search over roughly fourteen candidates that discarded every task an agent solved,
with screening decided on single trials. This is survivorship selection with an
uncontrolled multiple-comparisons problem: read the result as the tail of that
search, not as an unbiased estimate of long-horizon capability.

**No human baseline.** An upstream human implementation exists for each task, but
no human ran under the same 900-second limit, so "human-solvable" holds only in
the ordinary development sense.

## 6. The earlier round, and two findings worth your time

Nine earlier tasks — SemVer specification, SQL NULL semantics, certified
optimization, loop invariants, hash preimage, concurrency, timing-safe comparison,
asymptotic scale, exploit chaining — mostly failed as discriminators.

| Tasks | Outcome |
|---|---|
| A, B, D, F, G, H | Solved 5/5 by both agents |
| C | Passing artifact in all 10 trials; Fable always past the 900 s cap — a speed limit, not a capability gap |
| E | 0/5 both, but preimage search hardness no human beats in budget either. A declared G3(b)/G4 exception: a probe, not an admitted task |
| I | 0 valid trials — both platforms refused on safety grounds. A policy boundary, not measured inability; I did not attempt to bypass the safeguards |

**A validity defect in my own harness that inverted its conclusion.** Reading all
70 transcripts rather than trusting the aggregate revealed that every one of
Fable's trials leaving a readable transcript — **26 of 26** — could not execute a
single command: Claude Code creates its shell-snapshot directory at a fixed path
ignoring `TMPDIR`, my Seatbelt profile denied writes there, every command failed
with `EPERM`, and the process still exited 0. Nothing objected, because those
trials *passed*. **All 26 produced a verifier-passing artifact** — three-valued
SQL NULL semantics validated by differential fuzzing against real SQLite,
inductive invariants an SMT solver accepted, and two-phase locking with a global
lock order an exhaustive interleaving model checker could not break — without
running a line of code. That is the strongest evidence here that these tasks fall
to reasoning rather than iteration, and simultaneously a defect in my instrument.
After the fix: dead-shell signatures went from 26 of 26 to 0 of 27, the affected
agent got 51–67% faster on four tasks, and the control agent did not move.

**A reward-hack against my own grader.** In an early pilot, one Sol trial walked
`sys._getframe(2).f_back`, read the caller's locals, globals and code constants
for an integer in range, and "verified" each with SHA-256 before returning it — my
first grader ran the candidate in its own process, whose globals held the planted
secret. Grading is now out of process and the witness is discarded after use; the
saved exploit returns `honest_giveup`. The defensible claim is an exploit attempt
against a real vulnerability, not a reproducible pass. The methodology point
generalises: **I found the hole only by reading a *passing* transcript instead of
trusting a green check.**

## 7. Known defects in the current instrument

Disclosed rather than silently patched, because editing a verifier changes its
hash and invalidates every trial graded under it.

1. **An unexercised tamper surface.** Grading treats pytest's exit code as the
   pass signal, so a submission that edited the pre-existing
   `conans/test/conftest.py` to skip every test would be graded as passing. **No
   counted trial exercised it** — all twenty graded sandboxes were diffed against
   the pristine workspaces and none modified anything under `conans/test/`. Fixing
   this is the first change I would make before this harness certifies a *pass*.
2. **Task M's verifier is narrower than Task M's spec** — the multi-remote search
   and remote-failure resilience it requires have no test coverage, making M
   easier than its specification implies, which cuts against my own result.
3. **Isolation is benchmark-scoped and the solving phase is not network-isolated**,
   so the instruction not to fetch the upstream PR is unenforced. This can only
   produce false *passes*; none occurred.
4. **One harness file's pre-fix source is unrecoverable**, so the claim that a
   late evidence-sealer change was post-grading only is corroborated rather than
   proven.

Two further limits: both source PRs merged in late 2023, so the models may have
trained on the reference implementations — which cuts *toward* the negative result
but confounds any future pass; and every counted Fable trial left only a 15-byte
log stub, so its reasoning cannot be reconstructed.

## 8. Verify it yourself

Python 3.11+. No agent runs or API access needed — these read committed evidence.

```bash
python -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt

# The reported result: screening (k=1), confirmation (k=4), N/Fable replacements (k=4)
python harness/aggregate.py --run-dir evidence/runs/20260725T224349.182262Z-8b9db2d7
python harness/aggregate.py --run-dir evidence/runs/20260726T034819.662937Z-ae330dd8
python harness/aggregate.py --run-dir evidence/runs/20260728T062925.254874Z-d6ec0450

# The earlier round: clean 70-trial run, the defective run kept for comparison,
# and the standalone Task H and Task I runs
python harness/aggregate.py --run-dir evidence/runs/20260725T030646.540246Z-f40db469
python harness/aggregate.py --run-dir evidence/runs/20260724T150421.630439Z-545ef5ed
python harness/aggregate.py --run-dir evidence/runs/20260725T152301.243134Z-d7bb0572
python harness/aggregate.py --run-dir evidence/runs/20260725T162204.945673Z-16ac1626
```

Expected: every M and N row reports `0 /` passes. In the confirmation bundle
N/fable shows `0 / 0` with `infra 4` — the quota failures, recorded as invalid.
The first valid trial of each pair comes from the screening run and trials 2–5
from the confirmation run, except N/Fable, whose trials 2–5 come from the
replacement run because its confirmation attempts were quota-invalid.

The aggregator reports nothing unless the bundle's SHA-256 digests and exact file
set match, the manifest is `completed`, the isolation attestation is present, and
every verdict satisfies the schema. Each bundle has two absolute path prefixes
redacted, with pre-redaction digests in the matching `…original-digests.json`.

Check the instrument itself:

```bash
python -m pytest -q harness/tests                                    # 60 passed
python tasks/M_conan_graph_explain/verifier/verify.py --self-test    # ref 10/10, baseline 2/10
python tasks/N_conan_platform_requires/verifier/verify.py --self-test # ref 41/41, baseline 11/41
```

Both self-tests print `"self_test_passed": true` with an empty `problems` list. No
agent result is accepted from a task whose gate fails. Two isolation tests skip
outside the workspace root, so a fresh clone elsewhere reports 58 passed, 2
skipped.

Re-running the agents needs authenticated Claude Code and Codex CLIs and is
intentionally expensive; preflight fails closed unless each agent first executes a
command inside its real sandbox:

```bash
python harness/run_all.py --tasks M,N --agents fable,sol --k 5 \
                          --budget 900 --isolation strict
python harness/export_evidence.py --source-run results/runs/<run-id>
```

## 9. What I would do next

In order: fix the grader tamper surface and re-seal; tighten Task N's
specification on lock/platform resolution ordering and rerun, which would separate
the specification gap from the capability gap; preregister the task list and k so
the result stops being the tail of a search; use post-cutoff upstream changes to
remove the contamination confound; and add a same-budget human reference so "hard
for agents" is compared against something rather than asserted. A single passing
artifact under a materially identical replication would be important contradictory
evidence, and I would report it rather than hide it.

## 10. Disclosure

AI assistance was substantial. Codex was the primary hands-on contributor for this
round — candidate research, task packaging, specifications, verifiers, harness
fixes, execution and drafting. An independent Claude audit then reconstructed
every number from the raw verdicts and found the grader tamper surface, the Task N
specification gap and the Task M verifier narrowness reported above. I set the
objective and constraints, required the disclosure, reviewed the work, and decide
what to submit. It would be misleading to imply I authored every line.

Repository layout: [`REPORT.md`](REPORT.md) (the longer record),
[`tasks/`](tasks/) (fourteen packages, each with an agent-visible `workspace/` and
hidden `verifier/`), [`evidence/runs/`](evidence/runs/) (sealed manifests and
verdicts), [`harness/`](harness/) (runner, aggregator, isolation, graders, tests).
