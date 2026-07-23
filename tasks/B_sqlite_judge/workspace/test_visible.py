"""Visible example tests for evaluate().

Run with:  python3 -m pytest test_visible.py -q

NOTE: these examples are all NULL-free and use a UNIQUE dept_id in
active_departments. They illustrate the basic shape of the query but do not
exercise every rule in SPEC.md (in particular the NULL / three-valued-logic
rules and join multiplicity). Passing all of these is neither necessary nor
sufficient for credit -- see README.md.
"""
from evaluate import evaluate


def _names(db):
    return sorted(evaluate(db))


def test_basic_include():
    db = {
        "employees": [{"name": "Alice", "dept_id": 1, "manager_id": 7}],
        "active_departments": [{"dept_id": 1}],
        "banned_managers": [],
    }
    assert _names(db) == ["Alice"]


def test_manager_banned_excludes():
    db = {
        "employees": [{"name": "Bob", "dept_id": 1, "manager_id": 7}],
        "active_departments": [{"dept_id": 1}],
        "banned_managers": [{"banned_id": 7}],
    }
    assert _names(db) == []


def test_dept_not_active_excludes():
    db = {
        "employees": [{"name": "Carol", "dept_id": 2, "manager_id": 7}],
        "active_departments": [{"dept_id": 1}],
        "banned_managers": [],
    }
    assert _names(db) == []


def test_multiple_employees_multiple_depts():
    db = {
        "employees": [
            {"name": "Dan", "dept_id": 1, "manager_id": 7},
            {"name": "Erin", "dept_id": 2, "manager_id": 8},
            {"name": "Frank", "dept_id": 3, "manager_id": 9},
        ],
        "active_departments": [{"dept_id": 1}, {"dept_id": 2}, {"dept_id": 3}],
        "banned_managers": [{"banned_id": 8}],
    }
    assert _names(db) == ["Dan", "Frank"]


def test_manager_not_in_banned_list_included():
    db = {
        "employees": [{"name": "Grace", "dept_id": 1, "manager_id": 42}],
        "active_departments": [{"dept_id": 1}],
        "banned_managers": [{"banned_id": 1}, {"banned_id": 2}, {"banned_id": 3}],
    }
    assert _names(db) == ["Grace"]


def test_unique_dept_ids_one_to_one():
    db = {
        "employees": [
            {"name": "Heidi", "dept_id": 5, "manager_id": 1},
            {"name": "Ivan", "dept_id": 6, "manager_id": 2},
        ],
        "active_departments": [{"dept_id": 5}, {"dept_id": 6}],
        "banned_managers": [{"banned_id": 99}],
    }
    assert _names(db) == ["Heidi", "Ivan"]
