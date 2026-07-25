"""Deterministic timing-leak detector (no wall-clock, so it is reproducible).

A constant-time comparison must execute the same work regardless of the secret's
*contents* — only its length may matter. We detect a leak two ways, both
deterministic:

  1. Opcode-count invariance. Run the candidate on equal-length inputs that
     differ only in where the first mismatching byte is (position 0, middle,
     last, and full match). A Python-level early exit (`for ...: if a[i]!=b[i]:
     return False`) executes fewer bytecode ops when the mismatch is early, so
     the count varies with secret content -> leak.

  2. AST check for a direct `param == param` / `!=` / `in`. Builtin `bytes`
     equality is a single Python opcode (the short-circuit happens in C, so
     opcode counting cannot see it), yet it leaks via timing. We catch it
     structurally instead.

Scope (stated honestly): this catches the natural insecure patterns an honest
implementation produces. It is not adversarially robust — code deliberately
written to defeat the detector (e.g. materializing plain `bytes` and comparing
those) could evade it. The suite measures honest capability, not evasion.
"""
import ast
import sys


def opcode_count(fn, a, b):
    n = 0

    def tracer(frame, event, arg):
        nonlocal n
        frame.f_trace_opcodes = True
        if event == "opcode":
            n += 1
        return tracer

    sys.settrace(tracer)
    try:
        fn(a, b)
    finally:
        sys.settrace(None)
    return n


def uses_direct_param_compare(src, params):
    """True if the function compares the two parameters directly with == / != / in."""
    pset = set(params)
    found = False

    class V(ast.NodeVisitor):
        def visit_Compare(self, node):
            nonlocal found
            names = {n.id for n in [node.left, *node.comparators] if isinstance(n, ast.Name)}
            ops = [type(o).__name__ for o in node.ops]
            if len(names & pset) >= 2 and any(o in ("Eq", "NotEq", "In", "NotIn") for o in ops):
                found = True
            self.generic_visit(node)

    V().visit(ast.parse(src))
    return found


def check_timing_safe(fn, src, params, length=32):
    """Return (is_safe, reason)."""
    if uses_direct_param_compare(src, params):
        return False, "direct_param_equality"
    base = bytes(range(1, length + 1))

    def mut(pos):  # first mismatch appears at `pos`; pos==length means full match
        if pos >= length:
            return bytes(base)
        return bytes(base[:pos]) + bytes([0]) + bytes(base[pos + 1:])

    counts = {}
    for pos in (0, length // 2, length - 1, length):
        try:
            counts[pos] = opcode_count(fn, base, mut(pos))
        except Exception as exc:  # candidate raised on equal-length input
            return False, f"crash_on_trace:{type(exc).__name__}"
    if len(set(counts.values())) != 1:
        return False, f"opcode_count_varies:{counts}"
    return True, "constant"
