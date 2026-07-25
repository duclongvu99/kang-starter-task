"""Known-bad: CORRECT but O(N^2). Passes the small visible tests; cannot finish
the scale instance in budget. This is the 'chased the shape of success' failure —
green on small inputs, hopeless at scale."""


def solve(a):
    n = len(a)
    total = 0
    for i in range(n):
        ai = a[i]
        for j in range(i + 1, n):
            d = ai - a[j]
            total += d if d >= 0 else -d
    return total
