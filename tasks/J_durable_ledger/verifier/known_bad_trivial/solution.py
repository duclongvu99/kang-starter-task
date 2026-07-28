class TransactionRejected(ValueError): pass
class TransactionConflict(ValueError): pass


def recover(disk):
    return {"accounts": {}, "applied": {}}


def apply(disk, txid, changes):
    return None

