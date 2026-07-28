# Email draft to Professor Kang — starter task submission

**Subject:** Re: Starter task — two configuration-bound 0/5 results, and what they don't show

Dear Professor Kang,

Thank you for the starter task. I built two long-horizon repository-evolution
tasks from real Conan features, and under a frozen 900-second task/model
configuration each produced **0/5 passing artifacts from Fable 5 in Claude Code
and 0/5 from GPT-5.6 Sol in Codex**, with near-miss margins rather than stalls —
Fable reached 39 of 41 hidden tests on the harder task, Sol 38 of 41. I want to
be precise about what that does and does not show: these two tasks survived an
adaptive search that discarded roughly a dozen candidates the agents solved,
five trials only bound the true per-trial success rate below about 45%, and I
did not run a human under the same budget. So I claim a reproducible,
configuration-bound observation at the current boundary — not that either model
"cannot" do this work.

Both tasks use frozen pre-change snapshots of the MIT-licensed Conan codebase.
Task M asks for `conan graph explain`: graph/API/CLI integration, lexicographic
binary-distance ranking, and text/JSON compatibility. Task N generalizes system
tools into platform requirements across profiles, resolution, revisions,
lockfiles, package IDs, generators, metadata, and legacy compatibility. For each
I wrote a self-contained specification, froze the upstream base commit, kept the
trusted reference and hidden tests out of the agent workspace, required
reference-pass and baseline-fail, graded out of process, and sealed the manifests
and verdicts with SHA-256. Three commands in the README regenerate every number
in the report from the committed bundles.

Two things in my own instrument that I would rather tell you than have you find.
First, Task M is the clean result (both agents plateaued at 2–5 of 10 tests),
but Task N's residual gap is partly a specification gap: the two tests Fable
failed in all four final trials hinge on resolving platform requirements before
consulting the graph lock, my spec says only that lockfiles "enforce them on
replay", and the workspace's own visible legacy test asserts the opposite
precedence. Four independent trials all took the legacy reading, which I think
is evidence about my spec as much as about the model. Second, the grader has an
unexercised tamper surface — it treats pytest's exit code as the pass signal, so
a submission that edited the pre-existing `conans/test/conftest.py` to skip
everything would be scored as passing. No counted trial did this (I diffed all
twenty graded sandboxes), and I disclose rather than patch because changing the
verifier would invalidate the trials under my own versioning rule; the fix is
the first thing I would do before this harness ever certifies a pass.

The rest of the process is in the report and research log: two original tasks I
designed were solved during screening, a third Conan task was rejected after
both agents left passing artifacts, and I fixed a too-short CLI preflight, an
evidence-sealing failure caused by test-created symlinks, and a false
authentication classifier that mistook the source location `:401:` for an HTTP
401. Four Fable quota failures are recorded as invalid trials, not model
failures. No passing artifact for either task exists in any run, including the
two I did not count.

AI assistance was substantial and I do not want to overstate my hand. Codex was
the primary hands-on contributor for research, task packaging, specifications,
verifiers, harness fixes, execution, and drafting; an independent Claude audit
then reconstructed every number from the raw verdicts and found the two defects
above. I set the objective, required the disclosure, reviewed the work, and
decide what to submit.

I have attached the report, task packages, and checksum-sealed verdict bundles,
and I would welcome the chance to discuss the design — particularly whether the
specification-gap-versus-capability-gap distinction in Task N can be separated
cleanly, which seems to me the interesting measurement question underneath this.

Best regards,
Long Duc Vu
