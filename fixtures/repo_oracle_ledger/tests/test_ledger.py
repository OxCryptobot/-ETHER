import pytest
from ledger import Ledger


def test_open_and_balance():
    led = Ledger()
    a = led.open("alice", 100)
    assert a.balance == 100
    assert led.get("alice").balance == 100


def test_transfer_moves_money():
    led = Ledger()
    led.open("alice", 100)
    led.open("bob", 0)
    led.transfer("alice", "bob", 40)
    assert led.get("alice").balance == 60
    assert led.get("bob").balance == 40


def test_transfer_preserves_total():
    led = Ledger()
    led.open("alice", 100)
    led.open("bob", 50)
    before = led.total()
    led.transfer("alice", "bob", 25)
    assert led.total() == before == 150


def test_transfer_insufficient_raises():
    led = Ledger()
    led.open("alice", 10)
    led.open("bob", 0)
    with pytest.raises(ValueError, match="insufficient"):
        led.transfer("alice", "bob", 50)
    assert led.get("alice").balance == 10
    assert led.get("bob").balance == 0


def test_total_single():
    led = Ledger()
    led.open("x", 42)
    assert led.total() == 42


def test_duplicate_open_raises():
    led = Ledger()
    led.open("a", 1)
    with pytest.raises(ValueError):
        led.open("a", 2)
