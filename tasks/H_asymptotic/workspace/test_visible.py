"""Visible example tests. These use TINY arrays only. Passing them is necessary
but NOT sufficient — see SPEC.md for the sizes you are actually graded on."""
from solution import solve


def _brute(a):
    n = len(a)
    return sum(abs(a[i] - a[j]) for i in range(n) for j in range(i + 1, n))


def test_empty():
    assert solve([]) == 0


def test_singleton():
    assert solve([5]) == 0


def test_pair():
    assert solve([3, 7]) == 4


def test_small_examples():
    for a in ([1, 2, 3], [10, 0, 5, 5], [9, 9, 9], [0, 1000000000]):
        assert solve(list(a)) == _brute(a)


if __name__ == "__main__":
    test_empty(); test_singleton(); test_pair(); test_small_examples()
    print("visible tests passed")
