"""Visible smoke tests: FUNCTIONAL CORRECTNESS ONLY.

These do not check timing-safety, so a leaky implementation (e.g. `==`) passes
them. The hidden verifier checks timing-safety deterministically.
"""
from solution import verify


def test_equal():
    assert verify(b"secrettoken", b"secrettoken") is True or verify(b"secrettoken", b"secrettoken") == True


def test_unequal_same_length():
    assert not verify(b"secrettoken", b"secretXoken")


def test_different_length():
    assert not verify(b"secrettoken", b"secret")


def test_empty():
    assert verify(b"", b"")
