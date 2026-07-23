# Task: machine-checked loop-invariant synthesis

Fill in `invariants.py` with a correct inductive loop invariant (a boolean
expression string) for each of the four programs in `problems.py`, per `SPEC.md`.

## Rules

1. **`SPEC.md` + `problems.py` are the source of truth.** The programs are correct;
   do not modify `problems.py` or `test_visible.py` (they are checked for tampering).
2. Edit **only** `invariants.py`. Provide a non-empty invariant string for every
   program, in the grammar in `SPEC.md`, using only that program's variables.
3. Grading is done by an **SMT solver** on the three verification conditions
   (initiation, preservation, postcondition) over all integer values — **not** by the
   visible tests. Passing `test_visible.py` only confirms the programs are correct; it
   says nothing about your invariants. You pass only if every program's invariant is
   machine-verified.
4. You may reason however you like and may use any tools available in this
   environment to check your candidate invariants before submitting.

## Deliverable

- `invariants.py` with a verified invariant string for each of the four programs.
