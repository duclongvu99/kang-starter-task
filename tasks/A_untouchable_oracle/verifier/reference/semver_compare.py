"""Reference solution for Task A (correct, spec-faithful). Used only by the
grader-validity gate; never shown to candidate agents."""


def _sign(x: int) -> int:
    return (x > 0) - (x < 0)


def _parse(v: str):
    core, _plus, _build = v.partition("+")     # build metadata ignored (rule 4)
    main, _dash, pre = core.partition("-")
    major, minor, patch = (int(p) for p in main.split("."))
    return (major, minor, patch), (pre.split(".") if pre else [])


def _cmp_pre(a, b) -> int:
    if not a and not b:
        return 0
    if not a:
        return 1
    if not b:
        return -1
    for x, y in zip(a, b):
        xn, yn = x.isdigit(), y.isdigit()
        if xn and yn:
            c = _sign(int(x) - int(y))
        elif xn:
            c = -1
        elif yn:
            c = 1
        else:
            c = _sign((x > y) - (x < y))
        if c:
            return c
    return _sign(len(a) - len(b))


def compare(a: str, b: str) -> int:
    (a_main, a_pre), (b_main, b_pre) = _parse(a), _parse(b)
    c = _sign((a_main > b_main) - (a_main < b_main))
    return c if c else _cmp_pre(a_pre, b_pre)
