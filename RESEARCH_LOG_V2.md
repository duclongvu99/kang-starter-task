# Research log v2 — finding genuine capability failures

Date: 2026-07-28 (Asia/Ho_Chi_Minh)

## Claim discipline

This experiment does **not** try to prove that a model can never solve a task.
The strongest permitted result is operational and configuration-bound:

> 0 successful artifacts in *k* valid independent trials using the named model,
> CLI, prompt, isolation mode, wall-clock budget, task snapshot, and verifier.

A timeout by itself is not evidence: the remaining artifact is still graded. A
timeout is a valid bounded-budget failure only when the CLI otherwise ran, the
verifier completes, the artifact fails, and no infrastructure signature is
present. A policy refusal, CLI crash, quota/rate-limit event, dead tool sandbox,
or verifier infrastructure failure makes the attempt invalid. A task is not a
survivor if either target agent produces one passing artifact during screening.
Any post-result task/spec/verifier edit creates a new task version and
invalidates prior trials for the edited version.

## Why the new search changed direction

The original A–I set did not establish the requested result. Most tasks were
solved by both agents; Task C exposed only an agent-specific clean-run issue;
Task E was dominated by an inadmissible brute-force requirement; Task I caused
policy refusals rather than capability attempts.

Current benchmark evidence points to long-horizon software evolution,
high-complexity state machines, and concurrency/crash semantics as more useful
frontiers than short puzzle-like functions:

- SWE-EVO: <https://arxiv.org/abs/2512.18470> and
  <https://github.com/SWE-EVO/SWE-EVO>
- CONCUR: <https://arxiv.org/abs/2603.03683>
- LLM-FSM: <https://arxiv.org/abs/2602.07032>

The literature informed candidate selection; it is not substituted for direct
tests of Fable 5 and GPT-5.6 Sol in this repository.

## Screening funnel

| Key | Candidate | Mechanism | Self-test | Screening result |
|---|---|---|---|---|
| J | Crash-consistent exactly-once ledger | torn writes, atomic publish, retry idempotence | reference passes; four known-bads fail | **Rejected:** Fable 1/1 and Sol 1/1 passed |
| K | Re-entrant transactional reactive store | nested savepoints, callback waves, alias isolation, error aggregation | reference passes; three known-bads fail | **Rejected:** Sol 1/1 passed; Fable attempt invalid because Bun segfaulted |
| L | Conan `core:warnings_as_errors` evolution | policy propagation and exception-safe audit across 23 production files | reference 33/33; baseline fails | **Rejected:** both agents left passing artifacts in an exploratory run |
| M | Conan `graph explain` evolution | graph/API/CLI integration and lexicographic binary-distance ranking across 4 production files | reference 10/10; baseline fails | **0/5 both agents under the frozen configuration** (clean discriminator: artifacts plateau at 2-5/10) |
| N | Conan platform requirements evolution | profile/graph/lock/package-ID/generator semantics across 9 production files | reference 41/41; baseline fails | **0/5 both agents under the frozen configuration** (near boundary: 39/41 x4; residual gap partly a spec gap, see below) |

Task N caveat recorded after an adversarial audit: all four final Fable
artifacts failed exactly `TestPlatformRequiresLock::test_platform_requires_range`
and `TestToolRequiresLock::test_system_tool_require_range`. Both require
resolving platform requirements before consulting the graph lock, reversing the
pre-existing order. `SPEC.md` states only "Lockfiles record resolved platform
versions and enforce them on replay", while the workspace's visible,
non-editable legacy test asserts the opposite precedence. Four independent
trials took the legacy reading, so N's residual failure is at least partly
attributable to the specification rather than to the model.

J and K remain in the repository as negative research results. They must not be
presented as model failures.

## Frozen real-repository task provenance

The L–N workspaces are MIT-licensed Conan snapshots. Each specification is
self-contained and deliberately more explicit than the originating changelog.
Trusted reference and hidden-test patches are stored only under each verifier.

- L: base `aa844b6ba2bf6092f047741253a2080fa3cd9a2f`, upstream
  <https://github.com/conan-io/conan/pull/15149>
- M: base `f0a1b35fb7e93afee367ab530c6fb0b6a95795d2`, upstream
  <https://github.com/conan-io/conan/pull/14694>
- N: base `3f3fd457096f976799781f0fcb55c36d6662d619`, upstream
  <https://github.com/conan-io/conan/pull/14871>

These are not claimed as wholly invented features. The contribution here is the
task specification, frozen packaging, hidden/reference separation, mechanical
verifier, isolation, negative baseline, experiment protocol, and direct
cross-agent evidence.

## Trial protocol

Screening uses the existing common prompt, strict benchmark-scoped macOS
Seatbelt isolation, a live tool-use preflight, 900 seconds per agent attempt,
and out-of-process grading. Fable is invoked as `claude-fable-5` with at most 80
turns. Sol is invoked as `gpt-5.6-sol` with high reasoning effort. Both receive
the same task workspace and installed Python dependencies.

Only survivors proceed to confirmation. The intended confirmation rule is five
valid trials per agent on the exact frozen task. Invalid trials are rerun and
reported separately. A single passing artifact falsifies the proposed
"0/5 under this configuration" result for that task.

## Recorded evidence

- J run `20260725T174935.954486Z-0d4b6769`: both trials valid and passed.
- K run `20260725T175659.469658Z-fe2cde9a`: Sol valid and passed; Fable had
  zero valid attempts because Claude Code's Bun runtime segfaulted after the
  tool preflight. The crash is infrastructure evidence only.
- Preflight-only run `20260725T181100.824270Z-62dbeac9`: no trials ran because
  the five-second version-check timeout was too short for both installed CLIs.
  The timeout was raised to 60 seconds. This run is not capability evidence.
- Exploratory L–N run `20260725T181311.680930Z-a55d4656`: L received a passing
  artifact from each agent and was therefore rejected. M and N did not pass,
  but the run is not reportable confirmation evidence: Fable API connections
  closed on M/N; a loose authentication regex misread a Python source location
  ending in `:401:` as HTTP 401; and final sealing aborted because Conan tests
  left symlinks in agent-private scratch space. The scratch cleanup and auth
  classifier were fixed and regression-tested before rerunning.
- Sealed screening run `20260725T224349.182262Z-8b9db2d7`: M and N each had one
  valid failed artifact from each agent. The run has a completed manifest and
  verified SHA-256 evidence seal.
- Sealed confirmation run `20260726T034819.662937Z-ae330dd8`: M had four more
  valid failed artifacts from each agent; N had four more valid failed
  artifacts from Sol. All four N/Fable attempts were invalid infrastructure
  trials because the CLI returned `You're out of usage credits`; they are not
  counted as model failures. The run completed and its evidence seal verifies.
- Aborted resumed run `20260728T055232.710117Z-a49893fd`: after Fable credits
  were restored, all four N artifacts failed — two at 38/41 and two at 39/41 —
  but final sealing rejected a virtualenv symlink inside one sandbox. The run is
  diagnostic only and none of its four verdicts are counted.
- Sealed Fable replacement run `20260728T062925.254874Z-d6ec0450`: four fresh N
  attempts were valid and failed at 39/41. The task, verifier, prompt, Fable
  version/template, budget, grading timeout, concurrency, and isolation match
  screening. Only `run_all.py`/`aggregate.py` hashes differ due to the
  post-grading symlink-sealing fix. The evidence seal verifies.

The first two sealed manifests have identical task, verifier, prompt, harness,
and agent-version hashes. The replacement manifest differs only in the
post-grading sealer files as described above. All have the same Task N/verifier,
prompt, agent version/template, 900-second budget, concurrency 2, and strict
benchmark isolation.

Verifiability limit on that last sentence: the pre-fix `aggregate.py` is in
version control and its diff is confined to hashing symlink metadata without
following targets, but the corresponding pre-fix `run_all.py` (`b25abd5d...`) is
in no commit and cannot be recovered, so "sealer-only" is corroborated rather
than proven. Corroborating facts: the aborted run's own traceback shows the old
sealer ran inside `finalize_run` after every verdict was written; task,
verifier, prompt, agent version, template, budget, grading timeout, concurrency,
and isolation attestation are identical across all three runs; and all three
shipped bundles contain only regular files, so the symlink change cannot affect
their verification.

Combining only sealed reportable trials gives:

| Task | Agent | Artifact passes / valid trials | Invalid trials | Status |
|---|---|---:|---:|---|
| M | Fable 5 | 0/5 | 0 | five valid trials recorded |
| M | GPT-5.6 Sol | 0/5 | 0 | five valid trials recorded |
| N | Fable 5 | 0/5 | 4 quota failures outside the valid sample | five valid trials recorded |
| N | GPT-5.6 Sol | 0/5 | 0 | five valid trials recorded |

Which run contributes which valid trial: for M/Fable, M/Sol, N/Fable and N/Sol
the first valid trial comes from screening run `8b9db2d7` (k=1); trials 2-5 for
M/Fable, M/Sol and N/Sol come from confirmation run `ae330dd8` (k=4); trials 2-5
for N/Fable come from replacement run `d6ec0450` (k=4), because that pair's four
`ae330dd8` attempts were quota-invalid.

Statistical caveat: zero passes in five trials bounds the true per-trial success
rate below roughly 45% (95% Clopper-Pearson upper bound). This is an
observation, not a demonstration of impossibility. M and N are also the two
survivors of an adaptive search over roughly fourteen candidates that discarded
every task an agent solved, with screening decided on single trials, so the
result carries survivorship selection and an uncontrolled multiple-comparisons
problem.

For M, Fable passed between 2/10 and 5/10 hidden/regression tests per trial.
Sol passed between 2/10 and 4/10. For N, the screening Fable artifact passed
29/41 and all four sealed replacements passed 39/41; Sol passed 36/41 in four
trials and 38/41 in one. These are partial implementations, not evidence that
the models made no progress.

The confirmation run was wrapped in macOS `caffeinate` after earlier system
sleep made wall-clock observation confusing. This only prevented host sleep;
it did not change task files, prompts, isolation, or per-trial budgets. (This is
recorded from operating notes; it is not recoverable from the preserved run
artifacts.)

## Known defects in the instrument

Recorded after an adversarial audit, and disclosed rather than silently patched
because editing a verifier changes its hash and invalidates the trials graded
under it:

1. **Grader tamper surface.** `harness/repo_task_verifier.py` copies the whole
   submission, overlays only the hidden test files, and treats pytest's exit
   code as the pass signal. A submission that edited the pre-existing
   `conans/test/conftest.py` to skip every test would be graded as passing. All
   twenty counted sandboxes were diffed against the pristine workspaces and none
   modified anything under `conans/test/`, so no counted trial exercised this.
   Fix before any future *pass* is certified: restore `conans/test/` from the
   pristine snapshot before overlaying hidden tests, and assert a nonzero
   passed-count with zero skips.
2. **Task M verifier narrower than Task M spec.** The hidden patch edits
   `only_source_test.py::test_conan_test`, which the verifier's target list does
   not run, so two of the three required missing-binary guidance strings are
   never asserted; the multi-remote search and remote-failure-resilience
   requirements have no coverage. This makes M easier than its spec implies.
3. **Solving phase is not network-isolated.** Only the grading phase denies
   network; the no-fetch-the-upstream-PR rule is unenforced. This can only
   produce false passes, and none occurred.
4. **Contamination.** Both upstream PRs merged in late 2023 and are public, so
   both models may have trained on the reference implementations. This cuts
   toward the negative result, but a future pass could not be cleanly attributed
   to reasoning; replications should prefer post-cutoff changes.

Both tasks recorded 0/5 for both agents under the frozen configuration. The
claim remains configuration-bound, and one future pass under a materially
identical replication would be important contradictory evidence rather than
something to hide.
