"""Reference: correct AND efficient. O(N log N), Python big-int accumulation."""


def solve(a):
    b = sorted(a)
    total = 0
    prefix = 0
    for k, v in enumerate(b):
        total += v * k - prefix
        prefix += v
    return total
