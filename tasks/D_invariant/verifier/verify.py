"""Hidden verifier for Task D -- machine-checked loop-invariant synthesis.

The deciding check is an SMT solver (z3). For each program and the candidate
invariant `I`, z3 must PROVE all three Hoare verification conditions over all
integer values of the variables:

  (1) initiation:   pre               => I
  (2) preservation: I and guard       => I[body]
  (3) post:         I and not guard    => post

A VC is "proved" iff z3 finds the negation UNSAT. `sat` => a concrete
counterexample (VC false); `unknown` => not proved (treated as failure). A program
passes iff all three VCs are proved; the submission passes iff every program passes.

No LLM judge is involved. The verifier holds its OWN trusted copy of the program
definitions (an agent cannot weaken the VCs by editing problems.py). The z3
encoding is validated against the reference invariants and rejected bad invariants
by --self-test before any agent is graded.

Usage:
  python verify.py --submission <dir>
  python verify.py --self-test
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import sys

import z3

HERE = os.path.dirname(os.path.abspath(__file__))

# ---- Trusted copy of the program definitions (must match workspace/problems.py) ----
PROGRAMS = {
    "sum_odds": {
        "vars": ["n", "i", "s"],
        "pre": "n >= 0 and i == 0 and s == 0",
        "guard": "i < n",
        "body": {"s": "s + 2*i + 1", "i": "i + 1"},
        "post": "s == n*n",
    },
    "mult_by_add": {
        "vars": ["a", "b", "p", "i"],
        "pre": "a >= 0 and b >= 0 and p == 0 and i == 0",
        "guard": "i < a",
        "body": {"p": "p + b", "i": "i + 1"},
        "post": "p == a*b",
    },
    "int_sqrt": {
        "vars": ["n", "r"],
        "pre": "n >= 0 and r == 0",
        "guard": "(r+1)*(r+1) <= n",
        "body": {"r": "r + 1"},
        "post": "r*r <= n and n < (r+1)*(r+1)",
    },
    "sum_first": {
        "vars": ["n", "i", "s"],
        "pre": "n >= 0 and i == 0 and s == 0",
        "guard": "i < n",
        "body": {"s": "s + i", "i": "i + 1"},
        "post": "2*s == n*n - n",
    },
}

_CMP = {
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
}


class GrammarError(Exception):
    pass


def to_z3(expr_str, env):
    """Translate an expression string in the task grammar into a z3 expression.

    `env` maps variable name -> z3 expression (so we can substitute the body's
    next-state expressions for preservation checks). Anything outside the grammar
    raises GrammarError."""
    try:
        node = ast.parse(expr_str, mode="eval").body
    except SyntaxError as e:
        raise GrammarError(f"syntax: {e}") from e

    def rec(n):
        if isinstance(n, ast.Constant):
            if isinstance(n.value, bool) or not isinstance(n.value, int):
                raise GrammarError(f"only integer literals allowed, got {n.value!r}")
            return z3.IntVal(n.value)
        if isinstance(n, ast.Name):
            if n.id not in env:
                raise GrammarError(f"unknown variable {n.id!r}")
            return env[n.id]
        if isinstance(n, ast.BinOp):
            l, r = rec(n.left), rec(n.right)
            if isinstance(n.op, ast.Add):
                return l + r
            if isinstance(n.op, ast.Sub):
                return l - r
            if isinstance(n.op, ast.Mult):
                return l * r
            raise GrammarError(f"operator {type(n.op).__name__} not allowed")
        if isinstance(n, ast.UnaryOp):
            if isinstance(n.op, ast.USub):
                return -rec(n.operand)
            if isinstance(n.op, ast.Not):
                return z3.Not(rec(n.operand))
            raise GrammarError(f"unary {type(n.op).__name__} not allowed")
        if isinstance(n, ast.BoolOp):
            parts = [rec(v) for v in n.values]
            return z3.And(*parts) if isinstance(n.op, ast.And) else z3.Or(*parts)
        if isinstance(n, ast.Compare):
            terms = [rec(n.left)] + [rec(c) for c in n.comparators]
            conj = []
            for k, op in enumerate(n.ops):
                if type(op) not in _CMP:
                    raise GrammarError(f"comparison {type(op).__name__} not allowed")
                conj.append(_CMP[type(op)](terms[k], terms[k + 1]))
            return z3.And(*conj) if len(conj) > 1 else conj[0]
        raise GrammarError(f"construct {type(n).__name__} not allowed")

    return rec(node)


def _prove(formula):
    """Return 'proved' if `formula` is valid (its negation UNSAT), else
    'counterexample' or 'unknown'."""
    s = z3.Solver()
    s.set("timeout", 10000)
    s.add(z3.Not(formula))
    r = s.check()
    if r == z3.unsat:
        return "proved", None
    if r == z3.sat:
        return "counterexample", str(s.model())
    return "unknown", None


def check_program(name, inv_str):
    prog = PROGRAMS[name]
    zvars = {v: z3.Int(v) for v in prog["vars"]}
    result = {"vcs": {}, "passed": False}
    try:
        pre = to_z3(prog["pre"], zvars)
        guard = to_z3(prog["guard"], zvars)
        post = to_z3(prog["post"], zvars)
        inv = to_z3(inv_str, zvars)
        # next-state environment: each var mapped to its body update (old-state exprs)
        next_env = dict(zvars)
        for var, rhs in prog["body"].items():
            next_env[var] = to_z3(rhs, zvars)
        inv_next = to_z3(inv_str, next_env)
    except GrammarError as e:
        result["error"] = f"grammar:{e}"
        return result

    vc = {
        "initiation": z3.Implies(pre, inv),
        "preservation": z3.Implies(z3.And(inv, guard), inv_next),
        "post": z3.Implies(z3.And(inv, z3.Not(guard)), post),
    }
    all_proved = True
    for k, f in vc.items():
        status, cex = _prove(f)
        result["vcs"][k] = {"status": status}
        if cex and status == "counterexample":
            result["vcs"][k]["counterexample"] = cex
        if status != "proved":
            all_proved = False
    result["passed"] = all_proved
    return result


def _load_invariants(submission_dir):
    path = os.path.join(submission_dir, "invariants.py")
    if not os.path.exists(path):
        return None, "missing_invariants_py"
    spec = importlib.util.spec_from_file_location("submission_invariants", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:  # noqa: BLE001
        return None, f"import_error:{type(e).__name__}:{e}"
    inv = getattr(mod, "INVARIANTS", None)
    if not isinstance(inv, dict):
        return None, "no_INVARIANTS_dict"
    return inv, None


def grade(submission_dir):
    result = {"task": "D_invariant", "passed": False, "programs": {}, "failure_modes": []}
    invs, err = _load_invariants(submission_dir)
    if invs is None:
        result["failure_modes"].append(f"impl:{err}")
        return result

    all_pass = True
    for name in PROGRAMS:
        inv_str = invs.get(name, "")
        if not isinstance(inv_str, str) or not inv_str.strip():
            result["programs"][name] = {"passed": False, "error": "empty_invariant"}
            result["failure_modes"].append(f"{name}:empty_invariant")
            all_pass = False
            continue
        pr = check_program(name, inv_str)
        result["programs"][name] = pr
        if not pr["passed"]:
            all_pass = False
            if "error" in pr:
                result["failure_modes"].append(f"{name}:{pr['error']}")
            else:
                failed = [k for k, v in pr["vcs"].items() if v["status"] != "proved"]
                result["failure_modes"].append(f"{name}:VC_failed:{'+'.join(failed)}")
    result["passed"] = all_pass
    return result


def self_test():
    problems = []

    # (a) every VC must be a valid z3 formula and the prover must be well-behaved:
    #     a known tautology proves, a known falsehood gives a counterexample.
    x = z3.Int("x")
    if _prove(z3.Implies(x > 0, x >= 1))[0] != "proved":
        problems.append("prover failed on a tautology")
    if _prove(x > 0)[0] != "counterexample":
        problems.append("prover failed to refute a non-tautology")

    # (b) reference invariants must PASS all programs.
    ref = grade(os.path.join(HERE, "reference"))
    if not ref["passed"]:
        problems.append(f"reference did not pass: {ref['failure_modes']}")

    # (c) known-bad (postcondition-as-invariant) must FAIL.
    bad = grade(os.path.join(HERE, "known_bad_postcond"))
    if bad["passed"]:
        problems.append("known_bad_postcond PASSED (should fail)")

    # (d) trivial baseline (all empty) must FAIL.
    triv = grade(os.path.join(HERE, "known_bad_trivial"))
    if triv["passed"]:
        problems.append("known_bad_trivial PASSED (should fail)")

    print(json.dumps({
        "self_test_passed": not problems,
        "problems": problems,
        "reference_passed": ref["passed"],
        "reference_detail": {k: v["passed"] for k, v in ref["programs"].items()},
        "known_bad_postcond_passed": bad["passed"],
        "known_bad_postcond_failure_modes": bad["failure_modes"],
        "known_bad_trivial_passed": triv["passed"],
    }, indent=2))
    return 0 if not problems else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--submission")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        sys.exit(self_test())
    if not args.submission:
        ap.error("provide --submission <dir> or --self-test")
    print(json.dumps(grade(args.submission), indent=2))


if __name__ == "__main__":
    main()
