# Task: Prove It, Don't Just Return It — constrained assignment

Implement `solve(instance)` in `solution.py` exactly per `SPEC.md`.

## Rules — read carefully

1. **`SPEC.md` is the single source of truth for correct behavior.** Implement
   strictly to it — in particular §3 (the formal constraint model) and §4
   (the exact return-value contract for both the feasible and infeasible
   cases).
2. A visible test suite is provided in `test_visible.py`. You may run it as
   often as you like:
   `python -m pytest test_visible.py -q`
3. **Do not edit, delete, rename, weaken, skip, or `xfail` any test in
   `test_visible.py`, and do not add or remove test files.**
4. **The provided visible tests are only a few small, easy examples — they
   are not the grading battery and passing them is neither necessary nor
   sufficient.** Your submission is graded on an independent, held-out set
   of instances (including instances deliberately built to be infeasible,
   and instances sized so that greedy/heuristic solutions are
   cost-suboptimal or produce invalid assignments). Grading recomputes the
   true optimal cost / true feasibility / a true minimal certificate
   independently and compares your output against it — there is no reward
   for merely passing the visible tests.
5. You may use any library available in this environment, including
   `z3-solver` (`import z3`), to construct a solution you can argue is
   exactly (not approximately) correct. Using an exact solver is explicitly
   permitted — see SPEC.md §6.
6. Your `solve` will be called as a plain Python function,
   `solve(instance) -> dict`, on one instance at a time. It must not read
   from or write to the filesystem, and should return within roughly 60
   seconds per instance.

## Deliverables

- `solution.py` — a correct `solve(instance) -> dict` per `SPEC.md`.
