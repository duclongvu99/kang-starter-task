from framework import acquire, release, read, write


def transfer(src, dst, amt):
    """Transfer `amt` units from account `src` to account `dst`.

    This is a cooperative-concurrency *transaction*: a generator that performs
    shared-memory work by `yield from`-ing the framework operations (acquire,
    release, read, write). See SPEC.md for the framework and the exact
    correctness requirements. Your implementation must be correct under EVERY
    possible interleaving with other concurrent transfers and with a concurrent
    auditor -- not just the happy path exercised by test_visible.py.

    Replace this stub with your implementation.
    """
    raise NotImplementedError
    yield  # keeps `transfer` a generator function; remove once implemented
