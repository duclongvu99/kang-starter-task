"""Program definitions for the loop-invariant task (READ ONLY — do not edit).

Each program is a simple integer loop of the canonical form:

    # precondition `pre` holds here
    while guard:
        <simultaneous update `body`>
    # postcondition `post` holds here   (guaranteed: these programs are correct)

Every program is CORRECT: run on any inputs satisfying `pre`, it terminates with
`post` true. Your job is NOT to fix the program. Your job (in invariants.py) is to
supply, for each program, an INDUCTIVE LOOP INVARIANT that a solver can machine-check.

`pre`, `guard`, each `body` update, and `post` are expressions in this grammar
(your invariants must use the SAME grammar):

    expr   := integer literal | variable
            | expr (+|-|*) expr | -expr | ( expr )
    bool   := expr (==|!=|<|<=|>|>=) expr        # chained ok, e.g. 0 <= i <= n
            | bool (and|or) bool | not bool | ( bool )

Only the variables listed in each program's "vars" may appear. Integer semantics
are the mathematical integers (no overflow, no wraparound). `body` updates are
SIMULTANEOUS: all right-hand sides are evaluated in the pre-iteration state.
"""

PROGRAMS = {
    # s := sum of the first n odd numbers; s ends up equal to n*n.
    "sum_odds": {
        "vars": ["n", "i", "s"],
        "inputs": ["n"],
        "pre": "n >= 0 and i == 0 and s == 0",
        "guard": "i < n",
        "body": {"s": "s + 2*i + 1", "i": "i + 1"},
        "post": "s == n*n",
    },
    # p := a*b, computed by adding b to p, a times.
    "mult_by_add": {
        "vars": ["a", "b", "p", "i"],
        "inputs": ["a", "b"],
        "pre": "a >= 0 and b >= 0 and p == 0 and i == 0",
        "guard": "i < a",
        "body": {"p": "p + b", "i": "i + 1"},
        "post": "p == a*b",
    },
    # r := floor(sqrt(n)) by linear search.
    "int_sqrt": {
        "vars": ["n", "r"],
        "inputs": ["n"],
        "pre": "n >= 0 and r == 0",
        "guard": "(r+1)*(r+1) <= n",
        "body": {"r": "r + 1"},
        "post": "r*r <= n and n < (r+1)*(r+1)",
    },
    # s := 0+1+...+(n-1); at the end 2*s == n*n - n.
    "sum_first": {
        "vars": ["n", "i", "s"],
        "inputs": ["n"],
        "pre": "n >= 0 and i == 0 and s == 0",
        "guard": "i < n",
        "body": {"s": "s + i", "i": "i + 1"},
        "post": "2*s == n*n - n",
    },
}


# ---- a small interpreter so the visible tests can run the programs concretely ----
def _ev(expr, state):
    # `state` is a dict of int values; expr uses the grammar above (Python-compatible).
    return eval(expr, {"__builtins__": {}}, dict(state))  # noqa: S307 (trusted defs)


def run(name, **inputs):
    """Execute program `name` from a pre-state built out of `inputs`, return the
    final state dict. Raises AssertionError if `pre` does not hold."""
    prog = PROGRAMS[name]
    state = {v: 0 for v in prog["vars"]}
    state.update(inputs)
    assert _ev(prog["pre"], state), f"precondition false for {name} with {inputs}"
    steps = 0
    while _ev(prog["guard"], state):
        new = dict(state)
        for var, rhs in prog["body"].items():
            new[var] = _ev(rhs, state)
        state = new
        steps += 1
        if steps > 10_000_000:
            raise RuntimeError("loop did not terminate")
    return state


def postcondition_holds(name, **inputs):
    prog = PROGRAMS[name]
    return bool(_ev(prog["post"], run(name, **inputs)))
