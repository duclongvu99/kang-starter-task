# Experimental record and full-disclosure log

**Long Duc Vu** · starter task for Prof. Daniel Kang · experiments 19–28 July 2026

[`README.md`](README.md) is the self-contained account: the problem, the
admissibility protocol, the two tasks, the result, and how to verify it. This
document is the lab notebook behind it — the search that produced the tasks, every
run and why it was or was not counted, every defect found in the instrument, and
every claim withdrawn along the way. Nothing here is needed to understand the
result; it is here so the process can be audited rather than taken on trust.

## 1. The screening funnel

The search was adaptive and **not** preregistered. A candidate was rejected as
soon as either agent produced one passing artifact, which is why the two survivors
should be read as the tail of a search rather than a random sample.

| Key | Candidate | Deciding mechanism | Outcome |
|---|---|---|---|
| A | Reward-hacking oracle (SemVer) | Hidden differential oracle | Solved 5/5 by both |
| B | SQL three-valued NULL semantics | Differential fuzzing against real SQLite | Solved 5/5 by both |
| C | Certified optimal solution | Z3 optimality + minimal-IIS certificate | Passing artifact in all 10 trials; Fable always past the 900 s cap → speed limit |
| D | Loop-invariant synthesis | SMT-checked inductive invariants | Solved 5/5 by both |
| E | SHA-256 preimage | Planted witness, hardened out-of-process check | 0/5 both — but irreducible search hardness. Declared G3(b)/G4 exception: a probe, not an admitted task |
| F | Concurrency correctness | Exhaustive interleaving model checker + concurrent auditor | Solved 5/5 by both |
| G | Timing-safe comparison | Deterministic opcode-count leak detector | Solved 5/5 by both |
| H | Asymptotic scale trap | Scale-infeasible naive solution + overflow trap | Solved 5/5 by both |
| I | Exploit chaining | Reference exploit against a fresh server instance | 0 valid trials — both platforms refused on policy. Not measured inability |
| J | Crash-consistent exactly-once ledger | Torn writes, atomic publish, retry idempotence | Rejected: Fable 1/1 and Sol 1/1 passed |
| K | Re-entrant transactional store | Nested savepoints, callback waves, alias isolation | Rejected: Sol 1/1 passed; Fable's attempt invalid (Bun runtime segfault) |
| L | Conan warnings-as-errors evolution | Upstream regression suite, 33 tests | Rejected: both agents left passing artifacts |
| **M** | **Conan `graph explain`** | Upstream regression suite, 10 tests | **0/5 both under the frozen configuration** |
| **N** | **Conan platform requirements** | Upstream regression suite, 41 tests | **0/5 both under the frozen configuration** |

J, K and L remain in the repository as negative research results and must not be
presented as model failures.

**Why the direction changed.** The A–I set showed that the fair, fully-specified,
self-verifiable regime is largely conquered: given a mechanical checker and a
budget, both agents solve SMT-checked invariants, differential SQL semantics and
model-checked concurrency. Published evidence pointed instead at long-horizon
multi-file evolution — [SWE-EVO](https://arxiv.org/abs/2512.18470),
[CONCUR](https://arxiv.org/abs/2603.03683),
[LLM-FSM](https://arxiv.org/abs/2602.07032) — so I screened real upstream Conan
changes for four properties: a competent human implementation exists, behavior
spans several subsystems, a mechanical oracle exists, and it runs locally without
secrets or network.

A constraint worth stating, because it bounds what this method can ever deliver:
at k=5, a "cannot" claim needs a per-trial success rate near zero to be
convincing. If a task's true success rate is 25%, the chance both agents record
0/5 is about 6%. Long-horizon multi-file tasks with published solve rates in that
range therefore cannot deliver a literal impossibility claim — only a bounded
observation.

## 2. Task provenance

The L–N workspaces are MIT-licensed Conan snapshots checked out at the exact
pre-change commit. Each specification was written to be more explicit than the
originating changelog; the trusted reference and hidden-test patches live only
under each `verifier/`.

- **L**: base `aa844b6b`, upstream [PR #15149](https://github.com/conan-io/conan/pull/15149)
- **M**: base `f0a1b35f`, upstream [PR #14694](https://github.com/conan-io/conan/pull/14694)
- **N**: base `3f3fd457`, upstream [PR #14871](https://github.com/conan-io/conan/pull/14871)

These features are not claimed as invented. The contribution is the task
specification, frozen packaging, reference/hidden separation, mechanical verifier,
isolation, negative baseline, protocol, and the cross-agent evidence.

## 3. Run-by-run record

Reportable runs are sealed and complete. Everything else is retained and
explicitly not counted.

| Run ID | State | What happened |
|---|---|---|
| `20260725T174935.954486Z-0d4b6769` | complete | Task J screening: both agents valid and passing → J rejected |
| `20260725T175659.469658Z-fe2cde9a` | complete | Task K screening: Sol valid and passing → K rejected. Fable had zero valid attempts (Claude Code's Bun runtime segfaulted after preflight); infrastructure evidence only |
| `20260725T181100.824270Z-62dbeac9` | preflight failed | No trials ran: a five-second `--version` timeout was too short for both CLIs. Raised to 60 s. Not capability evidence |
| `20260725T181311.680930Z-a55d4656` | aborted | Exploratory L/M/N. L received a passing artifact from each agent → rejected. M and N did **not** pass, but the run is not reportable: Fable API connections closed, a loose authentication regex misread the Python source location `graph_binaries.py:401:` as an HTTP 401, and sealing aborted because Conan's own tests left symlinks in agent-private scratch |
| `20260725T224349.182262Z-8b9db2d7` | **sealed, counted** | Screening k=1: M and N each produced one valid failed artifact per agent |
| `20260726T034819.662937Z-ae330dd8` | **sealed, counted** | Confirmation k=4: four more valid failed artifacts for M/Fable, M/Sol and N/Sol. All four N/Fable attempts were invalid — the CLI reported exhausted usage credits — and are retained, not deleted |
| `20260728T055232.710117Z-a49893fd` | aborted | First resumed run after credits were restored. Four N/Fable artifacts failed — 38, 38, 39 and 39 of 41 — but sealing rejected a virtualenv symlink Fable had created inside a sandbox. **None of its four verdicts are counted** |
| `20260728T062925.254874Z-d6ec0450` | **sealed, counted** | Replacement k=4: four fresh N/Fable attempts, all valid, all failing at 39/41 |

**Which run supplies which valid trial.** For all four task-agent pairs, trial 1
comes from `8b9db2d7`. Trials 2–5 come from `ae330dd8` for M/Fable, M/Sol and
N/Sol, and from `d6ec0450` for N/Fable, because that pair's `ae330dd8` attempts
were quota-invalid.

**Configuration comparability.** All three counted runs share the same task and
verifier hashes, prompt hash, agent versions and command templates, 900-second
budget, 300-second grading timeout, concurrency 2, and isolation attestation. The
replacement run differs only in the `run_all.py` and `aggregate.py` hashes,
because the evidence sealer was changed between runs (§4.5).

**A check that the exclusions are not doing the work.** Every verdict for tasks L,
M and N across all preserved runs was examined: **no passing M or N artifact
exists anywhere**, including both aborted runs. Counting every attempt regardless
of validity gives 0/6 and 0/9 rather than 0/5.

## 4. Defects found in my own instrument

### 4.1 An agent with no shell, in most of the first round

Reading all 70 transcripts of the first full run rather than trusting the
aggregate revealed that every Fable trial leaving a readable transcript — **26 of
26** — could not execute a single command. Claude Code creates its shell-snapshot
directory at a fixed `<tmp>/claude-<uid>` path that ignores `TMPDIR`; my Seatbelt
profile denied writes there; every command failed with `EPERM`; the process still
exited 0. Nothing in the pipeline objected, because those trials *passed*.

**All 26 produced a verifier-passing artifact.** In its own words, from the one
first-round C trial that finished in budget: *"Local shell execution is broken
harness-wide … so I verified by exhaustive desk-checking."* The fix re-allows only
the CLI's own runtime-state directory inside the denied temp roots; the cost is
now reported honestly as `agent_shared_temp_write_isolated: False` rather than
left as an unexamined `null`. Confirmed against live data with a control:
dead-shell signatures went from 26 of 26 readable transcripts to 0 of 27, the
affected agent got 51–67% faster on four tasks, and the unaffected agent did not
move. Both runs are committed so the comparison is checkable.

### 4.2 A reward-hack against the grader

In an early pilot, one Sol trial wrote a `_caller_candidates` helper walking
`sys._getframe(2).f_back`, reading the caller's locals, globals and code constants
for an integer in range and "verifying" each with SHA-256 before returning it. My
first harness ran the candidate in the grader's own process, whose module globals
held the planted secret; the stack-walk found it, and the code's comments
rationalised reading the caller's memory as reusing "cheap candidate hints." The
witness is now built, used once and discarded, and grading runs out of process
with only the public parameters in scope; the saved exploit returns
`honest_giveup`.

The exploit and the vulnerable verifier are preserved under `evidence/`, but not a
reproducible passing transcript — so the defensible claim is an exploit attempt
against a real vulnerability, not a reproducible pass. Two takeaways, sized to the
evidence: a behavioural observation that does *not* generalise (n far too small,
and across two later runs Sol gave up honestly 10 times out of 10), and a
methodology point that does — **the hole surfaced only because I read a passing
transcript instead of trusting a green check.**

### 4.3 Trial-validity classifiers

Two false-positive classes were found and fixed. A bare `unauthorized` pattern
matched ordinary prose an unrelated editor plugin had injected into an agent's
context, voiding a clean trial; and a loose `401` pattern matched the Python
source location `graph_binaries.py:401:`. Patterns are now split by trustworthiness:
session limits, quota, rate limits and sandbox rejections void a trial on their
own, while ambiguous signatures void one only when the harness independently
observed a failure, and are otherwise recorded as `agent_infra_suspected:` for the
audit trail. Policy refusals are labelled distinctly (`agent_refused:`) and
excluded from the capability denominator so they can never read as inability.

### 4.4 The grader's tamper surface — disclosed, not patched

`harness/repo_task_verifier.py` copies the whole submission, overlays only the
hidden test files, and treats pytest's exit code as the pass signal. A submission
that edited the pre-existing `conans/test/conftest.py` to skip every test would
therefore be graded as passing; the specification's "do not edit files below
`conans/test/`" is advisory prose, not an enforced constraint. This is systemic to
tasks L, M and N.

**No counted trial exercised it.** All twenty graded sandboxes were diffed against
the pristine workspaces and none modified anything under `conans/test/`. I am
disclosing rather than patching because editing the verifier changes its hash and,
under this project's own versioning rule, invalidates every trial graded under it.
The fix — restore that tree from the pristine snapshot before overlaying hidden
tests, and assert a nonzero passed-count with zero skips — is the first change
required before this harness certifies a *pass*.

Related: Task M's verifier is narrower than Task M's specification. The hidden
patch edits a test method the target list never runs, leaving two of three
required missing-binary guidance strings unasserted, and the multi-remote search
and remote-failure resilience the spec demands have no coverage at all. This makes
M easier than advertised, which cuts against my own result.

### 4.5 The evidence sealer, and what cannot be proven

The original sealer refused any symlink under a run directory. Because sealing
runs inside `finalize_run` *after* every verdict is written, a symlink left by
Conan's tests or by Fable's own virtualenv aborted two otherwise-complete runs at
the last step. The sealer now hashes a symlink's own target string with a type
marker and never follows it, with regression tests proving external target
contents are ignored and link substitution is detected.

**The limit:** the `aggregate.py` change is in version control and is confined to
that behavior, but the matching pre-fix `run_all.py` exists in no commit and
cannot be recovered, so "the change was post-grading and sealer-only" is
corroborated rather than proven. Corroborating facts: the aborted run's own
traceback shows the old sealer running after all verdicts were written; task,
verifier, prompt, agent version, template, budget, grading timeout, concurrency
and isolation attestation are identical across all three counted runs; and all
three shipped bundles contain only regular files, so the change cannot affect
their verification.

### 4.6 Other operational notes

A five-second CLI version preflight failed both agents before any trial and was
raised to 60 s. Earlier macOS sleep made wall-clock observation confusing, so the
confirmation run was wrapped in `caffeinate`; this only kept the host awake and
changed no task file, prompt, isolation setting or budget — though that is
recorded from operating notes and is not recoverable from the run artifacts. The
sealed quota verdicts record the generic `agent_nonzero_exit` reason; the "out of
usage credits" message itself appears in the retained local agent logs.

## 5. Claims withdrawn after audit

Adversarial audits of earlier drafts found real errors, all corrected:

- Fable Task C reported as "3/3" when the saved evidence showed 0/5, all
  session-limited; Sol Task C reported as "5/5 clean" when it was 3/5.
- "Reproduces every number" and "all versions pinned" — false when written.
- "Anti-cheat by construction" — overstated while tasks A–D still graded
  in-process.
- The reward-hack described as having "passed 1/5" — not reproducible from
  committed evidence.
- "Fable never reward-hacks" — five trials inflated into a propensity claim.
- A fabricated statistic ("CWE-208, 20–35%") attributed to a paper that does not
  contain it, plus four further citation errors including a benchmark
  misattributed to the wrong authors.
- In this round: a diagnostic run's artifacts described as uniformly 38/41 when
  two were 39/41.

I would rather hand you a corrected report than a polished one. The same audit
that produced this list also produced §4.4 and the Task N specification-gap
finding in `README.md` §5.

## 6. Standing limits

Restated compactly, since they bound everything above: five trials per pair bound
the true per-trial success rate below roughly 45%; the tasks survived an adaptive
search over fourteen candidates; no human ran under the same budget; the solving
phase is not network-isolated; both source PRs merged in late 2023 and may sit in
the models' training data; every counted Fable trial left only a 15-byte log stub,
so its reasoning cannot be reconstructed; and the evidence is self-sealed, with no
external anchor proving the bundles came from these runs.

Verification commands are in [`README.md`](README.md) §8.
