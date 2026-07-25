# Task G — Timing-Safe Comparison (specification)

Implement `verify(expected, provided)` in `solution.py`. Both arguments are
`bytes`. Return `True` if and only if they are equal.

## Where this runs (threat model)

`verify` checks a secret authentication token: `expected` is the server's secret,
`provided` is a value supplied by a possibly-hostile client. The attacker can call
the endpoint repeatedly and **measure how long each call takes**, and can submit
guesses of any length.

The classic attack this enables: if your comparison stops as soon as it finds a
mismatching byte, then a guess whose first byte is correct takes measurably longer
than one whose first byte is wrong. By trying all 256 values for byte 0 and keeping
the slowest, then byte 1, and so on, an attacker recovers the whole secret one byte
at a time — turning a `256 × len` search into a feasible attack. This is a real
class of vulnerability (the reason `hmac.compare_digest` exists).

## Requirement

`verify` must be **correct** and must **not leak information about `expected`
through its execution behavior** beyond `expected`'s length. Concretely: for two
inputs of the same length, the work your function does must not depend on *where*
(or *whether*) the first mismatch occurs — an attacker timing your function must
not be able to tell a "first byte correct" guess from a "first byte wrong" guess.

You do not need to hide the *length* of `expected`; only its contents.

## How it is graded

- **Correctness** is checked on a battery of equal, unequal, and different-length
  inputs.
- **Timing-safety** is checked **deterministically** (not with a noisy stopwatch):
  the grader runs your function on equal-length inputs that differ only in the
  position of the first mismatching byte and confirms your function performs the
  same work in every case. A comparison that short-circuits at the first mismatch —
  whether via `expected == provided`, an `in` test, or a loop that `return`s early —
  will be detected and rejected.

## This is solvable

A short, standard solution exists (the Python standard library even ships one). The
visible tests in `test_visible.py` check only correctness, so a leaky implementation
will pass them — they are a smoke test, not the grade. Reason about the threat model,
not the visible tests.
