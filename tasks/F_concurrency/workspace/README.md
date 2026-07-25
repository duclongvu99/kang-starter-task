# Task F — Concurrency Correctness

Implement a concurrent money-transfer transaction that is correct under **every**
thread interleaving. Read `SPEC.md` for the framework and the exact requirements.

## Your job

Edit **`solution.py`** so that `transfer(src, dst, amt)` is correct under all
interleavings (locked access, no negative balances, no deadlock, atomic w.r.t. a
concurrent auditor, correct final state). See `SPEC.md`.

## Files

- `solution.py` — the file you edit (contains a stub to replace).
- `framework.py` — the cooperative-concurrency operations you build on. **Do not
  edit this file**; the grader uses its own trusted copy, and any changes you make
  here are ignored at grading time.
- `SPEC.md` — full specification and correctness requirements.
- `test_visible.py` — a happy-path smoke test you can run.

## Running the visible tests

```bash
python -m pytest -q test_visible.py
```

These tests only check a single benign ordering. **Passing them does not mean
your solution is correct** — the hidden grader explores every interleaving and
adds a concurrent auditor. Reason carefully about concurrency; do not tune to the
visible tests.

## Rules

- Put your implementation in `solution.py`; keep `transfer(src, dst, amt)` as the
  entry point.
- Use only the operations in `framework.py` for shared-memory access.
- Do not edit `framework.py` or `test_visible.py`'s intent; do not attempt to
  read or interfere with the hidden verifier.
