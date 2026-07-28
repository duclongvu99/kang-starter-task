from durable import decode_state, encode_state


class TransactionRejected(ValueError): pass
class TransactionConflict(ValueError): pass


def recover(disk):
    return decode_state(disk.read_slot(disk.read_head()))


def apply(disk, txid, changes):
    state = recover(disk)
    for key, delta in changes.items():
        state["accounts"][key] += delta
    target = "b" if disk.read_head() == "a" else "a"
    disk.write_slot(target, encode_state(state))
    disk.flush_slot(target)
    disk.publish(target)

