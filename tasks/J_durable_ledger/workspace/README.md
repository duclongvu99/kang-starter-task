# Task J — Crash-consistent, exactly-once ledger

Read `SPEC.md`, then implement `solution.py`.  The only graded deliverable is
`solution.py`; do not modify `durable.py`.

Run the visible smoke tests with:

```bash
python -m pytest -q
```

The hidden verifier uses the same public `durable.py`, injects a power loss at
every durable-operation boundary (including torn slot flushes), and retries
transactions.  It does not inspect prose or use an LLM judge.

