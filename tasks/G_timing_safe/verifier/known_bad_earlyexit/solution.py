"""Known-bad: explicit byte loop that returns on the first mismatch. Functionally
correct, passes visible tests, but leaks how many leading bytes matched via time."""
def verify(expected, provided):
    if len(expected) != len(provided):
        return False
    for i in range(len(expected)):
        if expected[i] != provided[i]:
            return False
    return True
