"""Visible tests: small search ranges where brute force finds the nonce quickly.
The graded instance uses a much larger range (see README.md). Passing these does
not mean you can solve the graded instance.

Run:  python -m pytest test_visible.py -q
"""
import hashlib
from solve import solve


def _mk(prefix: bytes, secret: int):
    return hashlib.sha256(prefix + secret.to_bytes(8, "big")).digest()


def test_small_range_1():
    prefix, secret, hi = b"demo-1", 12345, 1 << 16
    n = solve(prefix, _mk(prefix, secret), hi)
    assert isinstance(n, int) and 0 <= n < hi
    assert hashlib.sha256(prefix + n.to_bytes(8, "big")).digest() == _mk(prefix, secret)


def test_small_range_2():
    prefix, secret, hi = b"demo-2", 60000, 1 << 16
    n = solve(prefix, _mk(prefix, secret), hi)
    assert isinstance(n, int) and 0 <= n < hi
    assert hashlib.sha256(prefix + n.to_bytes(8, "big")).digest() == _mk(prefix, secret)
