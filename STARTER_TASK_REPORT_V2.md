# Starter Task Report — Long-Horizon Repository Evolution

**Prepared for Professor Daniel Kang**
**Prepared by Long Duc Vu, with substantial AI assistance disclosed in §8**
**Experiment dates:** July 25–28, 2026

## 1. Result and claim discipline

I built two repository-evolution tasks from changes that human Conan maintainers
had already shipped upstream, and ran both against Fable 5 in Claude Code and
GPT-5.6 Sol in Codex. Under the frozen configuration below, **neither agent
produced a passing artifact in five valid trials on either task**.

| Task | Agent | Passing artifacts / valid trials | Invalid trials | Per-artifact hidden-test score |
|---|---|---:|---:|---|
| M — `conan graph explain` | Fable 5 | 0 / 5 | 0 | 2, 5, 2, 2, 2 of 10 |
| M — `conan graph explain` | GPT-5.6 Sol | 0 / 5 | 0 | 2, 4, 4, 2, 4 of 10 |
| N — platform requirements | Fable 5 | 0 / 5 | 4 (quota) | 29, 39, 39, 39, 39 of 41 |
| N — platform requirements | GPT-5.6 Sol | 0 / 5 | 0 | 36, 36, 36, 38, 36 of 41 |

Configuration: Claude Code 2.1.220 with `claude-fable-5` and at most 80 turns;
Codex CLI 0.144.6 with `gpt-5.6-sol` at high reasoning effort; 900 s wall clock
per attempt; concurrency 2; strict benchmark-scoped macOS Seatbelt isolation;
frozen task snapshot, verifier, and prompt (hashes recorded in every manifest).

The claim I am willing to defend is exactly this:

> Under the named model/CLI versions, common prompt, frozen task and verifier,
> benchmark-scoped isolation, and 900-second budget, each agent produced zero
> passing artifacts in five valid independent trials.

I am **not** claiming that either model cannot solve these tasks. Five trials
with zero passes bound the true per-trial success rate below roughly **45%**
(95% Clopper–Pearson upper bound), which is a long way from impossibility. Nor
is this a measured human advantage: a human implementation exists upstream for
each task, but I ran no human participant under the same 900-second limit, so
"human-solvable" holds only in the ordinary software-development sense.

Every number above regenerates from sealed evidence:

```bash
python harness/aggregate.py --run-dir evidence/runs/20260725T224349.182262Z-8b9db2d7   # screening, k=1
python harness/aggregate.py --run-dir evidence/runs/20260726T034819.662937Z-ae330dd8   # confirmation, k=4
python harness/aggregate.py --run-dir evidence/runs/20260728T062925.254874Z-d6ec0450   # N/Fable replacements
```

The aggregator refuses a bundle whose SHA-256 file set or digests do not match,
whose manifest is not `completed`, or whose verdicts violate the schema.

## 2. The two tasks

Each package contains a frozen MIT-licensed Conan snapshot, an agent-visible
`SPEC.md`, a trusted upstream reference patch and hidden regression-test patch
(both stored only under the verifier), an out-of-process grader, and a self-test
gate requiring the reference to pass and the untouched baseline to fail.

**Task M — implement `conan graph explain`.** The agent must reconstruct a
dependency graph, select a missing binary, search the local cache and enabled
remotes, rank candidates by a lexicographic distance over
platform/settings/options/dependencies, return all candidates tied at the best
distance, and keep the API, JSON, text, and existing missing-binary behavior
coherent. Reference: 4 production files, +255/−32. Hidden tests: 3 files,
+207/−4, yielding 10 selected tests. Baseline fails 8 of 10; reference passes
10/10. Base commit `f0a1b35fb7e93afee367ab530c6fb0b6a95795d2`, from public
[Conan PR #14694](https://github.com/conan-io/conan/pull/14694).

**Task N — generalize system tools into platform requirements.** The agent must
add `[platform_requires]`/`[platform_tool_requires]`, deprecate `[system_tools]`
as an alias, and keep the new `Platform` status coherent across profile
composition, exact/range/revision resolution, host/build separation, lockfiles,
package-ID modes, generator visibility, metadata, and API serialization.
Reference: 9 production files, +63/−48. Hidden tests: 4 files, +262/−39,
yielding 41 selected tests. Baseline passes 11 of 41; reference passes 41/41.
Base commit `3f3fd457096f976799781f0fcb55c36d6662d619`, from public
[Conan PR #14871](https://github.com/conan-io/conan/pull/14871).

I did not invent these features. My contribution is the packaging and the
measurement: converting real upstream changes into frozen, self-contained
specifications, separating reference and hidden tests from the agent workspace,
building the verifier and its negative controls, and running the evaluation.

## 3. What the failures actually were, and where they are weak

**The two tasks are not equally strong evidence, and I want to be direct about
that before you find it yourself.**

**Task M is the clean result.** Both agents plateaued far from passing — 2 to 5
of 10 tests for Fable, 2 to 4 for Sol — across five independent trials each.
The artifacts are real multi-file attempts, not stubs; they simply do not
implement a coherent distance model, formatter refactor, and CLI integration
together.

**Task N is a narrow miss on partly underdetermined behavior.** Fable's four
final artifacts each passed 39 of 41 and failed *the same two tests*:
`TestPlatformRequiresLock::test_platform_requires_range` and
`TestToolRequiresLock::test_system_tool_require_range`. Both hinge on resolving
platform requirements *before* consulting the graph lock, which reverses the
pre-existing ordering. My `SPEC.md` states only "Lockfiles record resolved
platform versions and enforce them on replay" — and the workspace's *visible,
un-editable* legacy test asserts the **opposite** precedence ("even if the
profile points to another version the locked one will prevail"). Four
independent trials all chose the legacy reading. The honest reading is that
Task N's residual gap is at least partly a specification gap, not purely a
capability gap. Sol's best artifact (38/41) missed by a different margin.

So the defensible summary is: **one clean 0/5-by-0/5 task (M), and one
near-boundary 0/5-by-0/5 task (N) whose final failures sit on behavior my spec
underdetermines.**

## 4. Why these tasks, and what the selection process costs

My first nine candidates (A–I) mostly failed as discriminators. A, B, D, F, G
and H were solved 5/5 by both agents. C produced a verifier-passing artifact in
all ten trials — Sol cleanly at 482 s average, Fable in all five but always past
the 900-second cap — so C measures speed, not capability, and counts as solved
for task-selection purposes. Task E was a SHA-256 preimage: 0/5 for both, but
that is brute-force hardness a human could not beat in budget either, so I
rejected it as inadmissible. Task I drew policy refusals from both platforms and
produced zero valid capability attempts; I report that as a refusal boundary,
not as inability, and I did not attempt to bypass the safeguards.

Three further candidates fell in this round: both agents solved a
crash-consistent ledger (J), Sol solved a re-entrant transactional store (K),
and both left passing artifacts on a Conan warnings-as-errors task (L), which I
rejected conservatively.

I changed direction toward long-horizon software evolution on the evidence that
multi-file evolution is where frontier agents are weakest
([SWE-EVO](https://arxiv.org/abs/2512.18470),
[CONCUR](https://arxiv.org/abs/2603.03683),
[LLM-FSM](https://arxiv.org/abs/2602.07032)), then screened real upstream Conan
changes for four properties: a competent human implementation exists, behavior
spans several subsystems, a mechanical oracle exists, and it runs locally
without secrets or network.

**The cost of that process, stated plainly: M and N are the two survivors of an
adaptive, non-preregistered search over roughly fourteen candidates that
discarded every task an agent solved.** Screening decisions were made on single
trials. That is survivorship selection with an uncontrolled multiple-comparisons
problem, so this 0/5-and-0/5 result should be read as the tail of that search
rather than an unbiased estimate of long-horizon capability, and it should not
be generalized to long-horizon software evolution at large. A pre-registered
version — fixed task list, fixed k, no discarding after seeing results — is the
experiment I would run next, and I would expect a weaker result from it.

## 5. Instrument integrity, including what is wrong with it

The runner performs a live CLI and isolation preflight (each agent must execute
a command inside its real sandbox before any trial is scored, and the run fails
closed otherwise), creates a fresh sandbox per attempt, blocks access to the
verifier/reference and sibling trials, imposes the 900-second budget, records
invalid infrastructure attempts separately, and seals completed evidence with
SHA-256 checksums after every verdict is written. **A passing artifact counts as
a solve even if the agent timed out or exited nonzero** — grading is
unconditional and the reported metric is artifact passes over valid trials. A
quota failure, policy refusal, CLI crash, or verifier infrastructure failure is
recorded as invalid and never as a model failure.

Four defects and limits a reviewer should know:

1. **The grader has an unexercised tamper surface.** Grading copies the whole
   submission, overlays only the hidden test files, and treats pytest exit code
   0 as a pass. A submission that edited the pre-existing
   `conans/test/conftest.py` to skip every test would therefore be graded as
   passing; `SPEC.md`'s "do not edit files below `conans/test/`" is advisory
   prose, not an enforced constraint. **No counted trial exercised it** — I
   diffed all twenty graded sandboxes against the pristine workspaces and found
   zero modifications under `conans/test/`. I am disclosing rather than patching
   because editing the verifier would change its hash and, under this project's
   own versioning rule, invalidate all twenty trials. The fix — restore
   `conans/test/` from the pristine snapshot before overlaying hidden tests, and
   assert a nonzero passed-count with no skips — is the first change I would
   make before this harness is ever used to certify a *pass*.
2. **Task M's verifier is narrower than Task M's spec.** The hidden patch edits
   a test method (`only_source_test.py::test_conan_test`) that the verifier's
   target list does not run, so two of the three required missing-binary
   guidance strings are never asserted; the spec's multi-remote search and
   remote-failure-resilience requirements have no test coverage at all. This
   makes M easier to pass than its spec implies, which cuts against my own
   result rather than for it.
3. **Isolation is benchmark-scoped, and the solving phase is not
   network-isolated.** Authenticated agent CLIs retain their normal home/config
   access, and only the grading phase denies network. The instruction not to
   fetch the upstream PR is therefore unenforced. This can only produce false
   *passes*, and none occurred.
4. **One harness file's pre-fix source is unrecoverable.** The final N/Fable run
   used a changed evidence sealer, so its `run_all.py`/`aggregate.py` hashes
   differ from the earlier runs. The `aggregate.py` change is in version control
   and is confined to hashing symlink metadata without following targets. The
   corresponding `run_all.py` version is in no commit, so "the change was
   post-grading and sealer-only" is corroborated but not provable from preserved
   files. Corroboration: task, verifier, prompt, agent version, command
   template, budget, grading timeout, concurrency, and isolation attestation are
   identical across all three runs; the older sealer's own abort traceback shows
   sealing ran after all verdicts were written; and all three shipped bundles
   contain only regular files, so the symlink change cannot affect their
   verification.

## 6. Full-disclosure research record

This search was adaptive and is not preregistered. Beyond the screening funnel
in §4, the process exposed these events, each with a preserved run ID in
`RESEARCH_LOG_V2.md`:

1. A five-second `--version` preflight timeout failed both CLIs before any trial
   ran (`20260725T181100.824270Z-62dbeac9`). Raised to 60 s; not counted.
2. The first L/M/N run (`20260725T181311.680930Z-a55d4656`) ended unsealed
   because Conan's own tests left symlinks in agent-private scratch space. It
   also contained Fable connection closures and a loose authentication regex
   that misread the Python source location `graph_binaries.py:401:` as an HTTP
   401. Both were fixed and regression-tested; the run is not reportable
   evidence. Its M and N artifacts did not pass.
3. The confirmation run exhausted Fable usage credits after completing Task M.
   All four affected N/Fable trials were marked `valid=false`, `infra=true`, and
   remain in the evidence rather than being deleted. (Their sealed verdicts
   record the generic `agent_nonzero_exit` reason; the "out of usage credits"
   message itself is in the retained local agent logs.)
4. After credits were restored, the first resumed run
   (`20260728T055232.710117Z-a49893fd`) reached four failing verdicts — 38, 38,
   39, and 39 of 41 — but final sealing aborted because Fable had created
   `sandbox/.venv/bin/python3` as a symlink. **I did not count those four
   results.** I changed the sealer to hash a symlink's own target string with a
   type marker and never follow it, added regression tests proving external
   target contents are ignored and link substitution is detected, confirmed all
   prior bundles still verify, and reran all four attempts from the base
   snapshot.
5. Earlier macOS sleep made wall-clock observation confusing, so the
   confirmation run was wrapped in `caffeinate`. This only kept the host awake;
   task files, prompts, isolation, and budgets were unchanged. (This is asserted
   from my own operating notes; it is not recoverable from the preserved run
   artifacts.)

An earlier report from the A–I round contained claims I later withdrew after an
adversarial audit — incorrect Task C summaries, overclaims about isolation and
reproducibility, and an inadequately supported exploit result. That round's
first 70-trial run also had a Seatbelt profile that silently disabled Fable's
shell in every readable transcript, a teardown race, and a false-positive error
classifier. I fixed the harness, added the live tool preflight, and reran all 70
trials before reporting.

Retained runs are not deleted: I checked every verdict for tasks L, M, and N
across all preserved runs, and **no passing M or N artifact exists anywhere**,
including the two uncounted runs. Counting every attempt regardless of validity
would give 0/6 and 0/9 rather than 0/5, so the exclusions do not manufacture the
result.

## 7. What this evidence cannot establish

- **Statistical strength.** k=5 per pair; ~45% upper bound as in §1. The trials
  are procedurally independent (fresh sandbox, no shared state or cross-trial
  feedback), but neither CLI exposes a user-controlled random seed, so this is
  not proven statistical independence of model sampling — which weakens rather
  than merely qualifies any binomial reading of 0/5.
- **Reasoning transcripts.** Every counted Fable trial ended at the 900-second
  wall clock, and `claude -p` flushes at the end, so those trials left no
  readable transcript (the log is a 15-byte truncation). Their artifacts and
  verdicts are preserved and show substantial multi-file work, but their
  reasoning — and therefore their compliance with the no-fetch rule — cannot be
  reconstructed. Sol usually exited cleanly and its transcripts exist.
- **Contamination.** Both source PRs merged in late 2023 and are public, so both
  models may have seen the upstream implementations in training. This cuts
  *toward* the negative result — 0/5 despite possible memorization — but it
  means a future pass on these tasks could not be cleanly attributed to
  reasoning, and any replication should prefer post-cutoff changes.
- **Provenance of the bundles themselves.** Evidence is self-sealed; the
  checksums have no external anchor. A reviewer can verify internal consistency
  and reproduce every number, but cannot prove the bundles came from these runs.
- **Failure attribution.** Every counted Fable trial is a timeout with a graded
  failing artifact — "ran out of budget with incomplete work", not "concluded
  and was wrong". Sol mostly exited cleanly and was wrong. These are different
  failure modes and I report them separately rather than merging them.

## 8. AI assistance and ownership

AI systems contributed substantially. Earlier Claude Code and agent-assisted
audits helped build and correct the original benchmark. In this second search,
Codex was the primary hands-on contributor: it researched candidate directions,
designed J and K, identified and packaged the Conan tasks, wrote the
specifications, verifiers, and harness fixes, ran and audited the experiments,
and drafted this report. An independent adversarial audit by Claude then
reconstructed every number from the raw verdicts, found the grader tamper
surface, the Task N specification gap, and the Task M verifier narrowness
reported above, and rewrote the claim language. I set the objective and
constraints, required the disclosure, reviewed the work, and decide what to
submit. It would be misleading to imply I personally authored every line, and I
cannot derive a reliable human-versus-AI percentage from Git history.

## 9. Conclusion

Two frozen, real-world repository-evolution tasks on which Fable 5 and GPT-5.6
Sol each produced zero passing artifacts in five valid 900-second trials, with
fully reproducible, checksum-sealed evidence and the instrument's own defects
disclosed. Task M is the clean discriminator; Task N sits at the current
boundary — 39/41 four times — with residual failures on behavior my
specification underdetermines.

What would make this stronger, in the order I would do it: fix the grader tamper
surface and re-seal; tighten the Task N specification on lock/platform
resolution ordering and rerun, since that would separate the specification gap
from the capability gap; preregister the task list and k before running; use
post-cutoff upstream changes to remove the contamination confound; and add a
same-budget human reference so "hard for agents" can be compared against
something rather than asserted. A single passing artifact under a materially
identical replication would be important contradictory evidence, and I would
report it rather than hide it.
