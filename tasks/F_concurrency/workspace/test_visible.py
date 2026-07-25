"""Visible happy-path smoke tests (a single benign, sequential ordering).

These do NOT exercise adversarial interleavings or the auditor. Passing them does
not mean the solution is concurrency-correct -- the hidden verifier does that.
"""
from framework import run_sequential
from solution import transfer


def _run(transfers, accounts):
    return run_sequential([transfer(*t) for t in transfers], accounts)


def test_single_transfer():
    assert _run([("A", "B", 30)], {"A": 100, "B": 100}) == {"A": 70, "B": 130}


def test_chain_of_transfers():
    end = _run([("A", "B", 10), ("B", "C", 25)], {"A": 100, "B": 100, "C": 100})
    assert end == {"A": 90, "B": 85, "C": 125}
