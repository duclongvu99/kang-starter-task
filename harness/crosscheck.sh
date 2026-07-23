#!/usr/bin/env bash
# Legacy manual cross-check helper. Interactive setup is refused because a
# copied cwd is not an OS isolation boundary.
#
#   ./harness/crosscheck.sh setup A     # make an isolated copy of task A's workspace
#   # -> open Codex IN the printed directory, paste the prompt, let it finish
#   ./harness/crosscheck.sh grade A     # grade what the agent produced, with the hidden verifier
#
# Tasks: A B C D E
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="$ROOT/.venv/bin/python"

cmd="${1:-}"; task="${2:-}"
case "$task" in
  A) TDIR=A_untouchable_oracle ;;
  B) TDIR=B_sqlite_judge ;;
  C) TDIR=C_prove_it ;;
  D) TDIR=D_invariant ;;
  E) TDIR=E_preimage ;;
  *) echo "usage: $0 {setup|grade} {A|B|C|D|E}"; exit 1 ;;
esac
SANDBOX="/tmp/crosscheck_${task}"      # debug copy only; not an isolation boundary

case "$cmd" in
  setup)
    echo "REFUSED: placing a task in /tmp or changing cwd does not isolate an agent."
    echo "Use harness/run_all.py --tasks $task --isolation strict for reportable runs."
    exit 2
    ;;
  grade)
    [ -d "$SANDBOX" ] || { echo "no sandbox at $SANDBOX — run 'setup $task' first"; exit 1; }
    echo "Grading an existing UNSAFE DEBUG copy; this is not reportable evidence ..."
    "$VENV_PY" "$ROOT/tasks/$TDIR/verifier/verify.py" --submission "$SANDBOX"
    ;;
  *) echo "usage: $0 {setup|grade} {A|B|C|D|E}"; exit 1 ;;
esac
