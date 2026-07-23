"""Bounded SHA-256 preimage search. Implement `solve` per SPEC.md."""
import hashlib  # noqa: F401  (you will likely want this)


def solve(prefix: bytes, target: bytes, max_nonce: int):
    """Return an int nonce in [0, max_nonce) with
    sha256(prefix + nonce.to_bytes(8, "big")) == target, or "GIVE_UP"."""
    raise NotImplementedError
