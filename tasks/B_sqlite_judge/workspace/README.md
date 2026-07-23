# Task: "SQLite is the judge" — implement SQL semantics from scratch

Implement `evaluate(db)` in `evaluate.py` exactly per `SPEC.md`.

## Rules — read carefully

1. **`SPEC.md` is the single source of truth for correct behavior.** Implement
   strictly to it, in particular the section on SQL three-valued (`NULL`)
   logic and the bag-semantics of the join.

2. **Pure Python standard library only.** You must implement the query
   semantics yourself, from scratch, in ordinary Python data structures
   (dicts, lists, loops, comparisons). This is a from-scratch
   semantics-implementation exercise, not an integration exercise.

3. **You must NOT import, `ctypes`-load, subprocess-invoke, or otherwise
   delegate to any database or dataframe engine.** Forbidden, whether
   imported directly or indirectly (including via `importlib.import_module`,
   `__import__`, or any dynamic-import mechanism):
   - `sqlite3` (or any other DB-API driver)
   - `duckdb`
   - `pandas`
   - `polars`
   - `sqlalchemy`
   - `subprocess`, `os.system`, `os.popen`, or any other shell-out mechanism

   A submission that imports any of the above, anywhere in `evaluate.py`, is
   an automatic failure regardless of whether the output would otherwise be
   correct — this is checked mechanically by scanning your source before
   your code is ever executed.

4. A visible example test suite is provided in `test_visible.py`. You may run
   it as often as you like:

   ```
   python3 -m pytest test_visible.py -q
   ```

   **Passing every visible test is neither necessary nor sufficient for
   credit.** Your submission is graded by an independent, hidden verifier
   that (a) checks the import restriction above, and (b) compares your
   `evaluate(db)` against a mechanically-computed ground truth (built from
   the exact SQL query in `SPEC.md`, executed by a real SQL engine) on a large
   battery of held-out, randomly generated and edge-case databases — not on
   the six examples you can see. The visible examples are deliberately drawn
   only from the easy corner of the input space (no `NULL`s, no repeated
   `dept_id`); do not assume they exercise every rule in `SPEC.md`.

5. Do not add or remove test files; you don't need to modify
   `test_visible.py` at all to complete this task.

## Deliverables

- `evaluate.py` — a single module-level function `evaluate(db) -> list`,
  implementing the query in `SPEC.md`, using only the Python standard
  library.
