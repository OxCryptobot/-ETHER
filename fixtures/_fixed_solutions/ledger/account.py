"""Account model — part of multi-file ledger fixture."""
from __future__ import annotations


class Account:
    def __init__(self, name: str, balance: float = 0.0) -> None:
        self.name = name
        self.balance = float(balance)

    def credit(self, amount: float) -> None:
        if amount < 0:
            raise ValueError("amount must be non-negative")
        self.balance += amount

    def debit(self, amount: float) -> None:
        if amount < 0:
            raise ValueError("amount must be non-negative")
        if amount > self.balance:
            raise ValueError("insufficient funds")
        self.balance -= amount
