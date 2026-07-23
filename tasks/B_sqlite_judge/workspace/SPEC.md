# Specification: SQL NULL semantics + join multiplicity, in pure Python

Implement a single function in `evaluate.py`:

```python
def evaluate(db: dict) -> list:
    """Return the result MULTISET (a plain Python list; duplicates preserved,
    order irrelevant) of the fixed query defined below, evaluated against `db`."""
```

`db` is a plain Python dict with three keys, each mapping to a list of row-dicts:

```python
db = {
    "employees":           [ {"name": ..., "dept_id": ..., "manager_id": ...}, ... ],
    "active_departments":  [ {"dept_id": ...}, ... ],
    "banned_managers":     [ {"banned_id": ...}, ... ],
}
```

SQL `NULL` is represented as Python `None`. Any column may be `None` on any row
unless stated otherwise below.

## Schema

```
employees(name TEXT NULL, dept_id INT NULL, manager_id INT NULL)
active_departments(dept_id INT)   -- NON-UNIQUE: the same dept_id may appear on
                                  -- more than one row of this table.
banned_managers(banned_id INT NULL)  -- may contain NULL rows.
```

`active_departments.dept_id` is **not a key** — it may repeat. This is
deliberate: it is what drives join multiplicity below.

## The query to implement

English: for every employee whose department is currently active, list the
employee's name — unless that employee's manager is on the banned list.

Relational algebra:

```
π_name ( (employees ⋈_{dept_id} active_departments)
         ▷ σ_{manager_id ∉ banned_ids} )
```

Equivalent SQL (this is the exact query `evaluate` must reproduce — the hidden
grader runs this literal SQL against SQLite and diffs your output against it):

```sql
SELECT e.name
FROM employees e
JOIN active_departments d ON e.dept_id = d.dept_id
WHERE e.manager_id NOT IN (SELECT banned_id FROM banned_managers)
```

The result is a **bag** (multiset), not a set: if employee `e` matches more
than one row of `active_departments` (possible because `dept_id` is
non-unique there), `e.name` is emitted once **per matching row**. Duplicate
names across different employees are also preserved as-is. Row order does not
matter — the grader compares your list to the reference as a multiset
(`collections.Counter`), not as a sequence.

## SQL three-valued logic — read this carefully, it is the entire point of the task

SQL predicates do not evaluate to `TRUE`/`FALSE` only — they evaluate to
`TRUE`, `FALSE`, or `UNKNOWN`. Any comparison where an operand is `NULL`
evaluates to `UNKNOWN`, **not** `TRUE` and **not** `FALSE`. This includes
`NULL = NULL`, which is `UNKNOWN` (not `TRUE`) — `NULL` is never equal to
anything, including another `NULL`.

A row survives an `ON` clause or a `WHERE` clause **only if the predicate
evaluates to `TRUE`**. `UNKNOWN` is treated exactly like `FALSE` for the
purpose of "does this row survive" — but it is not the *same value* as
`FALSE`, which matters once it is combined with `NOT`, `AND`, `OR` (see
below).

Precisely, for this task:

1. **The join predicate** `e.dept_id = d.dept_id` is `UNKNOWN` whenever either
   side is `NULL`, and only `TRUE` when both are non-`NULL` and numerically
   equal. An employee with `dept_id IS NULL` **never** joins to anything —
   not even to an `active_departments` row that also happens to have a `NULL`
   `dept_id`.

2. **`x NOT IN (S)`**, where `S` is the multiset of values produced by
   `SELECT banned_id FROM banned_managers`, follows the standard SQL
   expansion `x NOT IN (S) == NOT(x = s1 OR x = s2 OR ... OR x = sn)`:
   - If `S` is **empty** (the `banned_managers` table has zero rows), the
     expansion is the empty disjunction, which is `FALSE`; negating it makes
     `x NOT IN (S)` **`TRUE`, for every `x`, even if `x IS NULL`.** (There is
     nothing to conflict with, so nothing rules it out — this holds
     regardless of whether `x` itself is `NULL`.)
   - If `S` is non-empty and contains **at least one `NULL`** value, then for
     *any* `x` (including non-`NULL` `x` that isn't equal to any element of
     `S`), the expansion contains an `UNKNOWN` disjunct (`x = NULL`) and no
     `TRUE` disjunct that would already prove membership, so the whole `OR`
     is `UNKNOWN` (never `FALSE`, because a `NULL` in `S` can never be ruled
     out as a possible match) — negating `UNKNOWN` is still `UNKNOWN`. So
     `x NOT IN (S)` is **never `TRUE`** whenever `S` contains any `NULL`,
     *regardless of `x`* — such rows never survive the `WHERE` clause, and
     if every `banned_managers` row you'd otherwise compare against carries
     a `NULL`, **no employee row can pass the filter**.
   - If `S` is non-empty, contains **no `NULL`**, and `x IS NULL`, every
     disjunct `x = si` is `UNKNOWN`, so the whole predicate is `UNKNOWN` —
     **not `TRUE`** — and the row does **not** survive.
   - If `S` is non-empty, contains no `NULL`, and `x` is non-`NULL`: ordinary
     set membership — `TRUE` iff `x` does not equal any element of `S`.

3. **Bag semantics of the join**: an `employees` row that matches `k` rows of
   `active_departments` (via equal, non-`NULL` `dept_id`) contributes its
   name **`k` times** to the pre-filter stream, before the `WHERE` clause is
   applied.

## Worked examples

| employees row | active_departments | banned_managers | result |
|---|---|---|---|
| `{name:"A", dept_id:1, manager_id:7}` | `[{dept_id:1}]` | `[]` (empty) | `["A"]` — empty `S` ⇒ `NOT IN` is `TRUE` |
| `{name:"A", dept_id:1, manager_id:None}` | `[{dept_id:1}]` | `[]` (empty) | `["A"]` — empty `S` ⇒ `TRUE` even though `manager_id IS NULL` |
| `{name:"A", dept_id:1, manager_id:7}` | `[{dept_id:1}]` | `[{banned_id:9}, {banned_id:None}]` | `[]` — `S` has a `NULL` ⇒ never `TRUE`, even though `7` isn't `9` |
| `{name:"A", dept_id:1, manager_id:None}` | `[{dept_id:1}]` | `[{banned_id:9}]` | `[]` — `manager_id IS NULL` and `S` non-empty ⇒ `UNKNOWN`, row excluded |
| `{name:"A", dept_id:None, manager_id:7}` | `[{dept_id:None}]` | `[]` | `[]` — `NULL = NULL` is `UNKNOWN`, never joins, even to a `NULL` on the other side |
| `{name:"A", dept_id:2, manager_id:9}` | `[{dept_id:2},{dept_id:2},{dept_id:2}]` | `[]` | `["A","A","A"]` — bag semantics, one copy per matching `active_departments` row |

## Assumptions you may rely on

- All `dept_id` / `manager_id` / `banned_id` values, when not `None`, are
  Python `int`. All `name` values, when not `None`, are Python `str`.
- You do not need to validate `db`'s structure; it always has all three keys,
  each mapping to a (possibly empty) list of dicts with exactly the columns
  named above.
- You are not required to preserve any particular ordering in the returned
  list — only the multiset of names matters.

See `README.md` for the rules governing *how* you may implement this
(pure Python, no database/dataframe engines).
