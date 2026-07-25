def verify(expected, provided):
    """Return True iff the two byte strings `expected` and `provided` are equal.

    This function checks an authentication token in a security-sensitive setting;
    see SPEC.md for the threat model. It must be correct *and* must not leak, through
    its execution behavior, any information about the secret `expected` beyond its
    length. Replace this stub with your implementation.
    """
    raise NotImplementedError
