# Task G — Timing-Safe Comparison

Implement a secure authentication-token comparison that does not leak the secret
through a timing side channel. Read `SPEC.md` for the threat model and the exact
requirement.

## Your job

Edit **`solution.py`** so that `verify(expected, provided)` returns `True` iff the
two byte strings are equal, **and** does not leak information about `expected`
(beyond its length) through its execution behavior. See `SPEC.md`.

## Running the visible tests

```bash
python -m pytest -q test_visible.py
```

These check **correctness only**. A leaky implementation (e.g. `expected == provided`)
will pass them — passing them does **not** mean the solution is timing-safe. The
hidden grader checks timing-safety deterministically.

## Rules

- Put your implementation in `solution.py`; keep `verify(expected, provided)` as the
  entry point.
- Do not attempt to read or interfere with the hidden verifier.
