"""Known-BAD submission for Task B's grader-validity gate: the forbidden-engine
cheat. This implementation is behaviorally CORRECT (it just runs the real
query through sqlite3) but must fail because it delegates to a forbidden
database engine instead of implementing the semantics itself. The hidden
verifier scans submission source for forbidden imports before ever executing
it, so this fails on the import-scan check regardless of its output.
"""
from __future__ import annotations

import sqlite3


_SQL = """
SELECT e.name
FROM employees e
JOIN active_departments d ON e.dept_id = d.dept_id
WHERE e.manager_id NOT IN (SELECT banned_id FROM banned_managers)
"""


def evaluate(db: dict) -> list:
    con = sqlite3.connect(":memory:")
    cur = con.cursor()
    cur.execute("CREATE TABLE employees (name TEXT, dept_id INT, manager_id INT)")
    cur.execute("CREATE TABLE active_departments (dept_id INT)")
    cur.execute("CREATE TABLE banned_managers (banned_id INT)")
    for r in db.get("employees", []):
        cur.execute(
            "INSERT INTO employees (name, dept_id, manager_id) VALUES (?, ?, ?)",
            (r.get("name"), r.get("dept_id"), r.get("manager_id")),
        )
    for r in db.get("active_departments", []):
        cur.execute(
            "INSERT INTO active_departments (dept_id) VALUES (?)", (r.get("dept_id"),)
        )
    for r in db.get("banned_managers", []):
        cur.execute(
            "INSERT INTO banned_managers (banned_id) VALUES (?)", (r.get("banned_id"),)
        )
    rows = cur.execute(_SQL).fetchall()
    con.close()
    return [row[0] for row in rows]
