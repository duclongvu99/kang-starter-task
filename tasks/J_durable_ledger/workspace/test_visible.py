import pytest

from durable import DurableDisk, make_image
from solution import TransactionRejected, apply, recover


def disk_with(accounts):
    return DurableDisk(make_image({"accounts": accounts, "applied": {}}))


def test_happy_path_and_retry():
    disk = disk_with({"alice": 100, "bob": 50})
    apply(disk, "rent-1", {"alice": -30, "bob": 30})
    assert recover(DurableDisk(disk.image()))["accounts"] == {"alice": 70, "bob": 80}
    before = disk.mutation_count
    apply(disk, "rent-1", {"alice": -30, "bob": 30})
    assert disk.mutation_count == before


def test_rejection_is_write_free():
    disk = disk_with({"alice": 10, "bob": 0})
    with pytest.raises(TransactionRejected):
        apply(disk, "bad", {"alice": -11, "bob": 11})
    assert disk.mutation_count == 0

