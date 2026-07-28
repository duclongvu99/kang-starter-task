import hashlib
from durable import canonical_json, decode_state, encode_state


class TransactionRejected(ValueError): pass
class TransactionConflict(ValueError): pass


def recover(disk):
    return decode_state(disk.read_slot(disk.read_head()))


def apply(disk, txid, changes):
    state = recover(disk)
    for key, delta in changes.items():
        state["accounts"][key] += delta
    state["applied"][txid] = hashlib.sha256(canonical_json(changes).encode()).hexdigest()
    target = "b" if disk.read_head() == "a" else "a"
    disk.write_slot(target, encode_state(state))
    # Wrong ordering: head may point at an empty/stale slot after a crash.
    disk.publish(target)
    disk.flush_slot(target)

