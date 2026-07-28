# Task K — Re-entrant transactional reactive store

Read `SPEC.md`, then implement `reactive_store.py`.  Run the visible smoke tests
with `python -m pytest -q`.  They cover only basic transactions; the hidden
verifier also exercises nested rollback, re-entrant callbacks, watcher-registry
changes, alias isolation, callback failures, and the reaction-wave limit.

The grade is produced by deterministic executable tests, not an LLM judge.

