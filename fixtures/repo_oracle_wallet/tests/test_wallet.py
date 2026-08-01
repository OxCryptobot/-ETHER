"""Project tests for the toy wallet — Phase B second oracle fixture."""

import pytest

from wallet import Wallet


def test_deposit_from_zero():
    w = Wallet()
    assert w.deposit(50) == 50.0
    assert w.balance == 50.0


def test_deposit_accumulates():
    w = Wallet(10)
    assert w.deposit(5) == 15.0
    assert w.balance == 15.0


def test_withdraw_ok():
    w = Wallet(100)
    assert w.withdraw(40) == 60.0
    assert w.balance == 60.0


def test_withdraw_insufficient_raises():
    w = Wallet(10)
    with pytest.raises(ValueError, match="insufficient"):
        w.withdraw(20)
    assert w.balance == 10.0


def test_negative_deposit_raises():
    w = Wallet()
    with pytest.raises(ValueError):
        w.deposit(-1)
