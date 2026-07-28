"""Implement Task J here."""


class TransactionRejected(ValueError):
    pass


class TransactionConflict(ValueError):
    pass


def recover(disk):
    raise NotImplementedError


def apply(disk, txid, changes):
    raise NotImplementedError

