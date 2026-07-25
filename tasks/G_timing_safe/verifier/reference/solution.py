"""Reference: constant-time comparison via the standard-library primitive
(hmac.compare_digest). Runs in time independent of the secret's contents."""
import hmac
def verify(expected, provided):
    return hmac.compare_digest(expected, provided)
