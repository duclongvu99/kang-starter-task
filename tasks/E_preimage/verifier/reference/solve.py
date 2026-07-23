"""The graded instance's witness was chosen at BUILD time, used once to compute the
target, verified to pass, then DISCARDED. It is deliberately not present at runtime
(neither in memory nor on disk), so no agent can recover it by reading files or by
introspecting the grader's process. See verify.py's build-time attestation."""
def solve(prefix, target, max_nonce):
    return "GIVE_UP"
