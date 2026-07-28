import pytest

from reactive_store import MISSING, Store


def test_coalesced_sorted_commit():
    store = Store({"b": 2, "a": 1})
    seen = []
    store.watch("*", lambda change: seen.append((change.key, change.old, change.new)))
    with store.transaction():
        store.set("b", 3)
        store.set("a", 9)
        store.set("b", 2)
        store.set("c", 4)
    assert seen == [("a", 1, 9), ("c", MISSING, 4)]


def test_nested_savepoint():
    store = Store({"x": 1})
    with store.transaction():
        store.set("x", 2)
        with pytest.raises(RuntimeError):
            with store.transaction():
                store.set("x", 3)
                raise RuntimeError("rollback inner")
        store.set("y", 4)
    assert store.snapshot() == {"x": 2, "y": 4}

