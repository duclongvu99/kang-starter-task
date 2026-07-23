"""Trivial do-nothing baseline for Task B's grader-validity gate. Must fail
the hidden verifier on essentially every non-trivial input."""
from __future__ import annotations


def evaluate(db: dict) -> list:
    return []
