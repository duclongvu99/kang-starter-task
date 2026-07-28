import hashlib
from durable import canonical_json, decode_state, encode_state


class TransactionRejected(ValueError): pass
class TransactionConflict(ValueError): pass


def recover(disk):
    return decode_state(disk.read_slot(disk.read_head()))


def apply(disk, txid, changes):
    state = recover(disk)
    fp = hashlib.sha256(canonical_json(changes).encode()).hexdigest()
    for key, delta in changes.items():
        state["accounts"][key] += delta
    state["applied"][txid] = fp
    # Wrong: a torn flush can destroy the only published copy.
    head = disk.read_head()
    disk.write_slot(head, encode_state(state))
    disk.flush_slot(head)

