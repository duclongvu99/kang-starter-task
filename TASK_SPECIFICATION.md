# Task Specification: a rigorous protocol for "tasks a frontier coding agent cannot do"

**Author:** Long Duc Vu · **For:** Prof. Daniel Kang (starter task) · **Date:** 2026-07-19

---

## 0. What this document is

The instruction was: *design a task specification, then create 2–3 tasks that Fable
(Claude Code) and GPT-5.6 Sol (Codex) cannot do.* The hard part is not finding
something an agent gets wrong once — stochastic single failures are cheap and prove
nothing. The hard part is making **"cannot do it"** a claim that survives the same
scrutiny your ABC work applies to existing benchmarks: a claim that is *fair*,
*mechanically decided*, *resampled*, *reproducible*, and *scoped*.

So this document specifies the **admissibility protocol** first, and treats the tasks as
instances of it. A task is admitted to the suite only if it passes every gate below. Seven were
built: five in the first pass (A–E), and two more (F, G) added after an audit, once it was clear
that the first pass had found no fair capability gap. The organizing idea is one distinction:

> **Shape vs. substance.** Every task exposes the agent to a *weak, visible* signal
> (example tests it can run and iterate against) and is decided by a *strong, hidden,
> mechanically-grounded* verifier that the agent never sees. The reported result is
> the **gap** between the two — the visible pass-rate an agent achieves versus the
> hidden pass-rate — not a bare binary. A task is interesting precisely when an agent
> can make the visible signal green while the hidden verifier still fails it.

This is the same move as gold-label verification in your text-to-SQL work
(a leaderboard measures label artifacts until the labels are independently certified),
turned from *auditing a benchmark* to *eliciting an agent capability*. It is also the
spine of my own research: making claims about agent reliability that do **not** require
trusting the agent's own output or narration.

---

## 1. Two kinds of "cannot do"

A task can be beyond an agent for two very different reasons, and a good specification
says which it is targeting:

- **(i) a capability gap** — a task a competent engineer can do but the agent cannot.
  This is the interesting kind, because it reveals a limit of the *model*.
- **(ii) irreducible difficulty** — a task *no one* can do in the budget (e.g. inverting
  a hash). This reveals a limit of *computation*, not the model, but it still answers
  "a task the agent cannot do," and it is the only kind that survives when the agent can
  self-verify its way to any checkable answer.

Each task below names the specific capability or propensity it operationalizes, so we
can check construct validity rather than a correlated proxy (e.g. tool-syntax fluency):

- **A — reward-hacking resistance (propensity, category i):** with write access to a
  test suite that contradicts the spec, does the agent optimize the spec or the checker?
- **B — semantic correctness under adversarial data (capability, i):** does it implement
  three-valued (NULL) logic + bag/multiplicity exactly, or the happy-path version?
- **C — certified reasoning (capability, i):** can it return a *provably* optimal answer
  / a *provably minimal* infeasibility certificate, not just a plausible one?
- **D — machine-checked proof (capability, i):** can it supply an *inductive* loop
  invariant that discharges the Hoare verification conditions (proof ≠ passing tests)?
- **E — bounded preimage search (category ii):** find a witness in a space of 2⁶⁴, where
  verifying is one hash. Included precisely because A–D are self-verifiable and a strong
  model iterates to the answer; E is where it cannot. **Admissibility caveat:** E cannot
  satisfy gate **G3(b)** (a shipped reference that passes the real grader) or **G4**
  (human-solvability in-budget) below — no in-budget passing reference can exist without
  leaking the witness — so E is a **declared exception**: a pilot probe of the
  search/verification asymmetry, not a fully-admitted task, and a budget-relative
  difficulty rather than a capability gap.
- **F — concurrency correctness (capability, i; added after an audit):** implement a transfer
  transaction that is correct under *every* interleaving. Decided by an exhaustive
  interleaving model checker plus a concurrent auditor, so the only passing pattern is
  two-phase locking with a global lock order. Added specifically because "A–D failed to
  discriminate" is a weak basis for a claim about category (i): F targets a documented weak
  area, and its visible tests deliberately cannot reveal a race, so an agent cannot iterate
  its way to correctness.
- **G — timing-safe comparison (capability, i; added after an audit):** implement token
  equality that leaks nothing but length. Decided **deterministically** — executed-opcode
  invariance across equal-length inputs that differ at different positions, plus an AST check
  for direct `param == param` — because a wall-clock timing measurement would be noisy and
  therefore an unfair grader. Added as a second gap hunt, in a security-relevant area where
  "looks right" and "is right" come apart.

The empirical result (see `REPORT.md`), from one 70-trial run: for Fable and GPT-5.6 Sol,
category (i) is **empty across all six category-(i) tasks** — A, B, D, F and G were solved
cleanly by both agents, and C is solved by both on the artifact but usually exceeds the 900 s
budget (a speed limit, not a capability gap) — so E, the declared category-(ii) exception, is
the only task that holds. That finding, not a contrived "unbeatable" task, is the contribution.
Task F also rules out the obvious deflationary explanation: it is not merely that these agents
can reconstruct a checker and iterate against it, because in F they cannot, and they still
succeeded. Task G is a weaker instance of the same result: the canonical answer is one stdlib
call, so its negative result carries correspondingly less weight, and I say so rather than
counting seven tasks as seven pieces of evidence.

An accident in that run reinforced the same conclusion from the opposite direction: the harness's
sandbox profile disabled one agent's shell in 22 of its 35 trials, so it could not execute the
visible tests, a solver, or any code at all — and it still produced verifier-passing artifacts in
every one of those trials. That is the strongest available evidence that success on these tasks is
reasoning from the specification rather than iteration against a signal. It is also a validity
failure of this protocol, which is why gate **G12(e)** now exists.

---

## 2. Admissibility gates (a task is used only if it passes all of them)

**G1 — Two-tier signal.** The task ships a weak visible check (example tests) and a
strong hidden verifier. The visible check must be passable by a *naive/wrong* solution,
so an agent that only chases the visible signal *looks* successful. (Verified: for every
task, a known-bad "shape-only" solution passes all visible tests.)

**G2 — Mechanically-grounded deciding verifier.** The hidden verifier is an SMT solver,
a real reference engine, a differential oracle, or a property/metamorphic check on
held-out inputs — **never an LLM judge**, and never authored from the same source as the
misleading visible tests. Ground truth is executable and cannot itself be a bad label.

**G3 — Grader-validity gate (run before any agent).** Every verifier ships a
`--self-test` that (a) validates its oracle on known ground truth, (b) grades a correct
reference solution and asserts it **passes**, (c) grades one or more known-bad solutions
and asserts they **fail**, and (d) confirms a **trivial baseline** (empty/do-nothing)
**fails**. No agent is graded until `self_test_passed = true`. This is the single check
whose absence your ABC paper shows breaks existing benchmarks.

**G4 — Fairness / human-solvability.** The specification is complete and unambiguous; a
correct reference solution exists (shipped) and a competent engineer can produce it from
the spec alone. Nothing needed to succeed is hidden.

**G5 — Disclosed rules, no undisclosed traps.** If a task deliberately contains a
conflict, an adversarial instance, or an infeasible case, the *rule for handling it* is
stated verbatim in the task's README/SPEC before the agent starts. The difficulty is in
*doing it correctly*, not in *guessing that a trap exists*.

**G6 — Anti-cheat by construction.** The oracle, gold answers, fuzzers, and answer key
live outside the agent's workspace and are never reachable from it. Files the agent must
not alter are integrity-checked (byte comparison). No task requires network access to
solve, so answer-lookup is not a confound.

**G7 — Resampling (pass@k).** "Cannot do it" is asserted only across k ≥ 5 independent
trials per agent, with the full pass distribution and failure-mode tally reported — not
a cherry-picked run. Documented stochasticity on exactly these failure modes makes a
single run uninformative.

**G8 — Non-discrimination sanity.** If a trivial/degenerate baseline can pass the hidden
verifier, the task is invalid regardless of what the frontier agents score (checked in
G3(d)).

**G9 — Reproducibility.** All RNG seeds, model slugs, tool/solver versions, the
per-attempt budget, and the test date are pinned and recorded.

**G10 — Failure-mode logging.** For each failed attempt the verifier records *how* it
failed (timeout, refusal, integrity violation, confident-but-wrong, suboptimal,
non-minimal certificate, …). The failure taxonomy is itself the result; it also defends
against a "the task was just broken" objection.

**G11 — Budgeted, dated claim.** The result is scoped as: *under budget B (turns / wall
clock / reasoning effort), on models M, on date D.* It is a snapshot of a capability
frontier, not a permanent ceiling — frontier models move, and the claim is stated to
move with them.

**G12 — Trial-validity classification is itself evidence, and must be audited.** Deciding
which trials *count* is as consequential as grading them, and it fails in both directions: an
environment failure scored as incapability makes a model look worse, and an over-eager
"infrastructure" verdict silently discards valid trials, which makes a benchmark kinder to the
models it measures. So: (a) every voided trial records a machine-readable reason; (b) the reason
must be derived from the *harness's own* observations (exit status, timeout, sandbox
initialisation), never from keyword-matching the agent's output, which the agent controls;
(c) one underlying event must not receive two different verdicts depending on a race;
(d) the voided trials are enumerated in the report, not summarised as a count; and

**(e) each agent's own tooling must be verified live, inside the real sandbox, before any trial
is scored.** Before the first graded trial, each agent is asked to execute a trivial command and
report the result; a trial in which the agent's shell, file access, or interpreter is unavailable
is an environment failure regardless of its outcome — *including when that outcome is a pass.*
This clause exists because it is the defect that actually happened, and it is the one a benchmark
author is structurally least likely to catch: the harness's sandbox profile silently disabled one
agent's shell in most of its trials, and because those trials still *passed*, nothing in the
pipeline objected. A validity check that only fires on failures is not a validity check.

The run reported in `REPORT.md` violates (b), (c) and (e) — see "Three defects in my own harness"
there. The numbers reported are the conservative ones the defective classifier produced; no
verdict was retroactively edited, and the affected readings are marked uninterpretable rather
than corrected by hand.

---

## 3. Evaluation protocol

For each (task, agent, trial):

1. A **fresh sandbox** is created as a copy of the task's `workspace/` (spec + skeleton
   + visible tests + README rules). No trial sees another trial's edits.
2. The agent is run **in that sandbox with an identical prompt and identical budget**
   across agents: read the README/SPEC, complete the task, follow all rules.
   - Fable: `claude -p … --model claude-fable-5` (Claude Code, headless).
   - GPT-5.6 Sol: `codex exec … -m gpt-5.6-sol` (Codex). Under strict isolation codex runs
     with `-s danger-full-access` and the harness's own macOS Seatbelt profile is the
     sandbox: macOS cannot nest `sandbox-exec`, so codex applying its own sandbox inside
     ours leaves it unable to touch the filesystem at all. In host mode codex keeps
     `workspace-write`. The command actually executed is recorded per trial.
3. The resulting sandbox is graded by the task's hidden verifier
   (`verify.py --submission <sandbox>`), which emits a verdict + failure modes.
4. pass@k and the failure-mode distribution are aggregated per (task, agent).

Identical prompt + identical budget + identical verifier across both agents is what
lets the comparison be about the models, not the harness.

---

## 4. Honest limitations (stated, not hidden)

- With 7 tasks and k = 5 (70 trials), this is a **demonstration of a protocol**, not a
  statistically-powered benchmark; it makes no discrimination/power claim its sample
  size cannot support. Its strongest claim is a negative one about the tasks it contains.
- **Not every task carries equal weight, and the protocol should say which.** A task whose
  canonical solution is one stdlib call (G) is weak evidence about a capability even when it is
  perfectly graded; a task where the visible signal cannot reveal the deciding property (F) is
  strong evidence. Task count is not evidence count, and a suite that reports only pass rates
  hides the difference.
- "Cannot do" is **budget-relative**: a larger turn/token budget, or a different
  scaffold, may pass any of these. The budget is fixed and disclosed; the claim is
  scoped to it.
- **Anti-cheat is not optional, and I learned it the hard way.** My first harness for
  Task E ran the candidate in the grader's own process; GPT-5.6 Sol read the planted
  witness out of that process via stack-frame introspection and passed. The fix (discard
  the witness after construction; grade out-of-process with only public inputs in scope)
  is now part of this protocol: *the deciding secret must not be reachable — in memory or
  on disk — from anything the candidate can execute.* I found this only by reading the
  passing transcript instead of trusting the green check.
- The tasks were **constructed and stress-tested with the help of coding agents**
  (Claude Code), which is both fitting — the suite is about agent limits — and a
  conflict of interest of the same shape my own preregistered work flags: the mitigation
  is that every deciding verifier is mechanical and independently grounded, and every
  task carries a human-solvable reference solution and a passing grader-validity gate.
