"""Implement evaluate(db) per SPEC.md.

db = {
    "employees":          [ {"name": ..., "dept_id": ..., "manager_id": ...}, ... ],
    "active_departments": [ {"dept_id": ...}, ... ],
    "banned_managers":    [ {"banned_id": ...}, ... ],
}

Return the result MULTISET (a plain list; duplicates preserved, order
irrelevant) of:

    SELECT e.name
    FROM employees e
    JOIN active_departments d ON e.dept_id = d.dept_id
    WHERE e.manager_id NOT IN (SELECT banned_id FROM banned_managers)

under standard SQL three-valued NULL semantics (see SPEC.md). Pure Python
standard library only -- see README.md for the list of forbidden imports.
"""
from __future__ import annotations


def evaluate(db: dict) -> list:
    raise NotImplementedError("implement evaluate() per SPEC.md")
