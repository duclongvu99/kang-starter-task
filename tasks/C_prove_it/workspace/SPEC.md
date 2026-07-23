# Specification: Constrained Assignment — Prove Feasibility/Optimality

Implement a single function in `solution.py`:

```python
def solve(instance: dict) -> dict:
    """See return-value contract below."""
```

## 1. The problem

You are given `N` jobs and `M` machines.

- Every job must be assigned to **exactly one** machine, chosen from a
  per-job **allowed set** of machines.
- Every machine has an integer **capacity**: the maximum number of jobs it
  may host simultaneously.
- Certain **pairs of jobs conflict**: two conflicting jobs may never be
  assigned to the same machine (they may still each be assigned to *some*
  machine, just not the *same* one).
- Every (job, machine) pair that is allowed has an integer **cost**. The
  total cost of an assignment is the sum, over all jobs, of the cost of the
  machine that job was assigned to.

The goal is to find a **minimum-cost** valid assignment. **Some instances
have no valid assignment at all** ("infeasible") — your solution must
correctly detect this, not just report a cost.

## 2. Instance schema (exact keys, no others assumed)

```jsonc
{
  "jobs":      ["j0", "j1", ...],           // list of job ids (strings)
  "machines":  ["m0", "m1", ...],           // list of machine ids (strings)
  "allowed":   {"j0": ["m0", "m2"], ...},   // job -> list of machines it may run on
                                             // (a subset of "machines"; may be empty)
  "capacity":  {"m0": 3, "m1": 1, ...},     // machine -> max number of jobs it may hold
                                             // (a nonnegative int; present for EVERY machine)
  "conflicts": [["j0", "j3"], ...],         // unordered pairs of job ids that may not
                                             // share a machine
  "cost":      {"j0": {"m0": 5, "m2": 9}, ...}  // job -> {machine -> nonnegative int cost}.
                                             // Defined for at least every machine in
                                             // allowed[job]; extra entries (if any) are
                                             // ignored and may be absent.
}
```

Guarantees you may rely on:

- Every job id in `"jobs"` appears as a key in `"allowed"` and in `"cost"`.
- Every machine id in `"machines"` appears as a key in `"capacity"`.
- Every machine id appearing inside `"allowed"` values is a member of
  `"machines"`.
- Job ids inside `"conflicts"` pairs are members of `"jobs"`. A conflict pair
  is unordered: `["a","b"]` and `["b","a"]` mean the same thing.
- `capacity` values are `>= 0`. An `allowed[job]` list may legitimately be
  **empty** (that job then has nowhere to go — see below).

## 3. Formal constraint model (this is the ONLY definition of correctness)

For job `j` and machine `m ∈ allowed[j]`, let `x[j,m] ∈ {0,1}` indicate that
job `j` is assigned to machine `m`. An assignment is **valid** iff:

1. **Exactly one machine per job**:
   for every job `j`, `Σ_{m ∈ allowed[j]} x[j,m] = 1`.
   (Consequence: if `allowed[j]` is empty, this sum is always `0`, so no
   valid assignment can include job `j` — the instance is infeasible.)
2. **Capacity**:
   for every machine `m`, `Σ_{j : m ∈ allowed[j]} x[j,m] ≤ capacity[m]`.
3. **Conflicts**:
   for every conflict pair `(j1, j2)` and every machine `m` with
   `m ∈ allowed[j1] ∩ allowed[j2]`: NOT (`x[j1,m] = 1` AND `x[j2,m] = 1]`).
   (I.e. `j1` and `j2` are never both assigned to the same machine `m`.)

An instance is **FEASIBLE** iff at least one valid assignment exists,
**INFEASIBLE** otherwise.

The **cost** of a valid assignment is `Σ_j cost[j][m_j]` where `m_j` is the
machine assigned to job `j`. For a feasible instance, the goal is the
assignment of **minimum** cost over all valid assignments.

## 4. Return-value contract

### Case A — the instance is feasible

```python
{"status": "optimal", "assignment": {"j0": "m2", "j1": "m0", ...}}
```

- `assignment` must contain **every** job in `instance["jobs"]` as a key,
  each mapped to a machine in that job's `allowed` list.
- The assignment must be **valid** per §3 (rules 1–3).
- Its total cost must equal the **true minimum cost** achievable by *any*
  valid assignment — not merely a cost that "looks good". Any valid but
  strictly-more-expensive assignment is graded as **wrong**, even if the
  excess is 1 unit. (If several assignments share the minimum cost, any one
  of them is accepted.)

### Case B — the instance is infeasible

```python
{"status": "infeasible", "certificate": ["j2", "j5", "j9"]}
```

`certificate` is a list of job ids and must be a **minimal infeasible
subset**:

- Let `S` be the set of job ids listed in `certificate` (`S` must be
  non-empty and a subset of `instance["jobs"]`, with no duplicates).
- Define `sub_instance(S)` as the instance restricted to just the jobs in
  `S`: same `machines` and `capacity`, `allowed`/`cost` restricted to jobs in
  `S`, and `conflicts` restricted to pairs where **both** endpoints are in
  `S`.
- **Infeasible-by-itself**: `sub_instance(S)` must itself have no valid
  assignment (per §3, applied to just the jobs in `S`).
- **Minimal**: for **every** job `j ∈ S`, `sub_instance(S \ {j})` (`S` with
  that one job removed) **must be feasible**. In other words, no job in your
  certificate may be dropped — each one is individually necessary to
  reproduce the contradiction. A certificate that is infeasible-by-itself
  but contains even one removable job is **wrong**.

There may be more than one valid minimal infeasible subset for a given
instance; any one of them is accepted.

## 5. What counts as "correct" (grading, informal summary)

Your submission is checked against an **independently computed** ground
truth (not against the example tests below), on instances you have never
seen:

- If the true instance is feasible and you say `"optimal"`: your assignment
  must be valid AND cost-optimal.
- If the true instance is feasible and you say `"infeasible"`: wrong, no
  matter what certificate you attach.
- If the true instance is infeasible and you say `"optimal"`: wrong, no
  matter how "valid-looking" your assignment is (it cannot actually be
  valid, by definition — check your feasibility logic).
- If the true instance is infeasible and you say `"infeasible"`: your
  certificate must be infeasible-by-itself AND minimal, as defined in §4.

There is no partial credit for "close" — a feasible-but-suboptimal
assignment fails, and a correct-but-non-minimal certificate fails.

## 6. On solving this correctly

This problem is a form of constrained assignment (related to generalized
assignment / bin-packing with side constraints), which is NP-hard in
general. **Greedy heuristics (e.g. "assign each job, in order, to its
cheapest currently-available allowed machine") are not sufficient**: they
can be optimal on small, slack instances and simultaneously be
cost-suboptimal, or produce conflict-violating assignments, or produce a
non-minimal/incorrect infeasibility certificate on harder instances.

You are explicitly **permitted and encouraged** to use an exact
optimization method to get a *provably* correct answer, for example:
- an SMT/ILP solver such as **z3** (`z3-solver`, available in this
  environment) using `Optimize()` for the minimum cost and `Solver()` /
  UNSAT checks for feasibility and for building a minimal infeasible
  certificate (e.g. by deleting jobs one at a time and re-checking
  feasibility — "deletion filtering"); or
- any other exact method (e.g. an ILP formulation via another solver, or a
  complete branch-and-bound search) that you can show always finds the true
  optimum / a true minimal certificate.

A solution that merely "looks plausible" on the example tests below is not
what is being graded here.

## 7. Scale

Expect instances with up to roughly 20 jobs and 10 machines in grading.
Your solution should return within about 60 seconds per instance — prefer
an efficient exact formulation (e.g. z3 `Optimize`/`Solver` with the
pseudo-boolean/linear constraints above) over brute-force enumeration of all
job→machine combinations.
