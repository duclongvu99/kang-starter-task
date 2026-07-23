"""Reference solution for Task B (correct, spec-faithful). Used only by the
grader-validity gate; never shown to candidate agents."""
from __future__ import annotations


def evaluate(db: dict) -> list:
    employees = db.get("employees", [])
    active_departments = db.get("active_departments", [])
    banned_rows = db.get("banned_managers", [])

    banned_empty = len(banned_rows) == 0
    banned_ids = [r.get("banned_id") for r in banned_rows]
    banned_has_null = any(b is None for b in banned_ids)
    banned_set = {b for b in banned_ids if b is not None}

    result = []
    for e in employees:
        dept_id = e.get("dept_id")
        manager_id = e.get("manager_id")

        # "manager_id NOT IN (SELECT banned_id FROM banned_managers)"
        if banned_empty:
            # Empty IN-list: the disjunction "x = s1 OR ... " is vacuously
            # FALSE for an empty list, so NOT IN is TRUE for every x,
            # including a NULL x.
            not_in_true = True
        elif banned_has_null:
            # A NULL anywhere in the list poisons the disjunction to
            # UNKNOWN (never FALSE), so NOT IN can never be TRUE.
            not_in_true = False
        elif manager_id is None:
            # x IS NULL against a non-empty, NULL-free list: every
            # comparison is UNKNOWN, so the whole disjunction is UNKNOWN.
            not_in_true = False
        else:
            not_in_true = manager_id not in banned_set

        if not not_in_true:
            continue

        # Join predicate: e.dept_id = d.dept_id. NULL = anything (including
        # NULL) is UNKNOWN, never TRUE, so a NULL dept_id never joins.
        if dept_id is None:
            continue

        for d in active_departments:
            if d.get("dept_id") == dept_id:
                result.append(e.get("name"))  # bag semantics: once per match

    return result
