"""Visible tests: confirm each program is CORRECT (its postcondition holds at
runtime) on a handful of concrete inputs. These do NOT test your invariants — the
invariant is graded separately by a solver on the held-out verification conditions.

Run:  python -m pytest test_visible.py -q
"""
import pytest
from problems import PROGRAMS, postcondition_holds


CASES = {
    "sum_odds": [{"n": 0}, {"n": 1}, {"n": 5}, {"n": 13}],
    "mult_by_add": [{"a": 0, "b": 7}, {"a": 4, "b": 0}, {"a": 6, "b": 9}],
    "int_sqrt": [{"n": 0}, {"n": 1}, {"n": 15}, {"n": 16}, {"n": 26}],
    "sum_first": [{"n": 0}, {"n": 1}, {"n": 10}, {"n": 100}],
}


@pytest.mark.parametrize("name", list(PROGRAMS))
def test_program_is_correct(name):
    for inputs in CASES[name]:
        assert postcondition_holds(name, **inputs), (name, inputs)
