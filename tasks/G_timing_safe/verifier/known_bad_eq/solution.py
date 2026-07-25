"""Known-bad: builtin equality. Functionally correct, passes visible tests, but
`bytes.__eq__` short-circuits in C at the first mismatching byte -> timing leak."""
def verify(expected, provided):
    return expected == provided
