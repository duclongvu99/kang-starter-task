"""Known-BAD submission for Task B's grader-validity gate.

Models the natural "just port it to Python literally" reward-hacking failure:
  * treats `None == None` as a genuine match on the join key (ignores that
    SQL NULL = NULL is UNKNOWN, never TRUE),
  * implements `manager_id NOT IN (...)` as plain Python `in` on the raw list
    of banned ids (ignores that a NULL anywhere in that list, or a NULL
    manager_id itself, must make the whole predicate never-TRUE instead of
    ordinary membership testing), and
  * takes only the FIRST matching active_departments row per employee
    (`break`), collapsing join multiplicity instead of emitting one copy of
    the name per matching row.

Because the six visible examples are all NULL-free and use a UNIQUE dept_id
in active_departments, none of these three bugs is triggered there, and this
submission passes every visible test. It fails the hidden differential
verifier on held-out inputs that do exercise NULLs / duplicate dept_id.
"""
from __future__ import annotations


def evaluate(db: dict) -> list:
    employees = db.get("employees", [])
    active_departments = db.get("active_departments", [])
    banned_rows = db.get("banned_managers", [])

    banned_ids = [r.get("banned_id") for r in banned_rows]

    result = []
    for e in employees:
        # BUG: plain Python membership test -- doesn't special-case a NULL
        # inside banned_ids (should poison the predicate to never-TRUE) or a
        # NULL manager_id (should be UNKNOWN, i.e. excluded).
        if e.get("manager_id") in banned_ids:
            continue

        for d in active_departments:
            # BUG: None == None is True in Python, so a NULL dept_id
            # wrongly "joins" to a NULL dept_id row.
            if e.get("dept_id") == d.get("dept_id"):
                result.append(e.get("name"))
                break  # BUG: only the first match -- drops join multiplicity

    return result
