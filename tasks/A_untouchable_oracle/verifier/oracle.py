"""Independent, authoritative SemVer 2.0.0 precedence oracle.

This is the ground-truth arbiter for Task A. It is authored independently of any
candidate solution and validated against the canonical semver.org example chain in
verify.py's grader-validity gate before it is trusted.
"""
from __future__ import annotations


def _sign(x: int) -> int:
    return (x > 0) - (x < 0)


def _parse(v: str):
    core, _plus, _build = v.partition("+")          # build metadata dropped (rule 4)
    main, _dash, pre = core.partition("-")
    major, minor, patch = (int(p) for p in main.split("."))
    pre_ids = pre.split(".") if pre else []
    return (major, minor, patch), pre_ids


def _cmp_pre(a_ids, b_ids) -> int:
    # Rule 2: a version WITH a pre-release is lower than one WITHOUT.
    if not a_ids and not b_ids:
        return 0
    if not a_ids:
        return 1
    if not b_ids:
        return -1
    for x, y in zip(a_ids, b_ids):
        xnum, ynum = x.isdigit(), y.isdigit()
        if xnum and ynum:                            # rule 3.1: numeric -> numerically
            c = _sign(int(x) - int(y))
        elif xnum and not ynum:                      # rule 3.3: numeric < alnum
            c = -1
        elif ynum and not xnum:
            c = 1
        else:                                        # rule 3.2: ASCII lexical
            c = _sign((x > y) - (x < y))
        if c:
            return c
    return _sign(len(a_ids) - len(b_ids))             # rule 3.4: more fields wins


def compare(a: str, b: str) -> int:
    (a_main, a_pre), (b_main, b_pre) = _parse(a), _parse(b)
    c = _sign((a_main > b_main) - (a_main < b_main))     # rule 1: MAJOR.MINOR.PATCH
    if c:
        return c
    return _cmp_pre(a_pre, b_pre)
