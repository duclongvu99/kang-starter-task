# Specification: machine-checked loop-invariant synthesis

For each of the four programs defined in `problems.py`, supply an **inductive loop
invariant** in `invariants.py`. Each program is a correct integer loop:

```
# pre holds
while guard:
    <simultaneous body update>
# post holds   (the programs are already correct — do not modify them)
```

## What you must produce

`invariants.py` maps each program name to an invariant string `I` (a boolean
expression over that program's variables, in the grammar below). For each program,
`I` is graded by an **SMT solver (z3)** that checks the three standard Hoare
verification conditions, over **all integer values** of the variables (not just the
ones the loop reaches):

1. **Initiation:** `pre => I`
2. **Preservation:** `I and guard => I[body]` — i.e. `I` with every variable
   replaced by its simultaneous body update still holds.
3. **Post:** `I and not guard => post`

`I` passes a program **iff all three are proved** (the solver finds the negation of
each unsatisfiable). Your submission passes **iff every program's invariant passes**.

## Why this is not trivial

The postcondition is usually **not** an inductive invariant. For example a loop that
ends with `s == n*n` typically needs an invariant relating the loop counter to the
partial result (something true on *every* iteration), which is strictly stronger in
some ways and weaker in others than the postcondition. Restating the postcondition as
the invariant will fail preservation (2); a too-weak invariant will fail (1) or (3).
Finding an `I` that threads all three is the task.

## Grammar (both the programs and your invariants use it)

```
expr := integer literal | variable
      | expr (+|-|*) expr | -expr | ( expr )
bool := expr (==|!=|<|<=|>|>=) expr        # chained comparisons ok: 0 <= i <= n
      | bool (and|or) bool | not bool | ( bool )
```

- Only the variables in a program's `vars` may appear in its invariant.
- Integers are the mathematical integers (no overflow / wraparound).
- No division, modulo, function calls, quantifiers, or other constructs.

## Fairness / solvability

Everything needed is given: each program's `pre`, `guard`, `body`, and `post` are in
`problems.py`, fully and unambiguously. A person comfortable with Hoare-logic loop
invariants can write all four by hand. Nothing is hidden; the grader recomputes the
verification conditions from the same program definitions you are given.

See `README.md` for the submission rules.
