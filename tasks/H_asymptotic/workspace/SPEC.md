# Task H — Sum of pairwise absolute differences

Implement `solve(a)` in `solution.py`.

## What to compute

Given a list `a` of non-negative integers, return

```
S = sum over all pairs of indices i < j of  |a[i] - a[j]|
```

as an exact integer.

## What you are graded on (read this — it is the whole task)

The visible tests in `test_visible.py` use tiny arrays. **They are not the
grading inputs.** Your `solve` is graded on hidden inputs with the following
disclosed properties, and it must be correct on all of them:

- **Size:** arrays with up to **4,000,000** elements.
- **Values:** each element is between 0 and 1,000,000,000 (10^9).
- **Magnitude of the answer:** the true sum can exceed 2^63, so it does **not**
  fit in a signed 64-bit integer. Return the exact value.
- **Budget:** each call to `solve` must return within **30 seconds** of
  wall-clock time. A call that does not return in time is scored as a failure.

There are no undisclosed traps: every constraint you must satisfy is stated
above. A correct, efficient solution exists and is short. The difficulty is in
meeting all four constraints at once, not in guessing what they are.

## Grading

Grading is mechanical and deterministic: your returned integer is compared,
exactly, against a value computed by a trusted reference on the same array. No
partial credit, no timing heuristics — either the returned integer is exactly
correct within budget on every hidden instance, or the task is not passed.

## Rules

- Edit only `solution.py`. Do not edit `test_visible.py` or add other graded files.
- No network access is needed or permitted.
- The Python standard library is available. If you use any third-party library,
  make sure your arithmetic stays exact at the magnitudes above.
