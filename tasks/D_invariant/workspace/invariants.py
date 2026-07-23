"""Supply an inductive loop invariant for each program in problems.py.

Each value is a STRING in the grammar described in problems.py (a boolean
expression over that program's variables). For each program, your invariant `I`
must satisfy all three verification conditions, which are checked by an SMT solver
over ALL integer values of the variables:

    (1) initiation:   pre  =>  I
    (2) preservation: I and guard  =>  I[body]     (I still holds after one iteration)
    (3) postcondition: I and not guard  =>  post

A correct-but-non-inductive predicate (e.g. just restating the postcondition) will
fail (2). Fill in each string.
"""

INVARIANTS = {
    "sum_odds": "",
    "mult_by_add": "",
    "int_sqrt": "",
    "sum_first": "",
}
