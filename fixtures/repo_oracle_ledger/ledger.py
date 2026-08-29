"""Ledger — intentional cross-file bugs.

BUGS:
- transfer credits destination but does not debit source
- total() double-counts by summing balances twice
"""
from __future__ import annotations

from typing import Dict

from account import Account


class Ledger:
    def __init__(self) -> None:
        self._accounts: Dict[str, Account] = {}

    def open(self, name: str, balance: float = 0.0) -> Account:
        if name in self._accounts:
            raise ValueError("account exists")
        acct = Account(name, balance)
        self._accounts[name] = acct
        return acct

    def get(self, name: str) -> Account:
        if name not in self._accounts:
            raise KeyError(name)
        return self._accounts[name]

    def transfer(self, src: str, dst: str, amount: float) -> None:
        if amount < 0:
            raise ValueError("amount must be non-negative")
        a = self.get(src)
        b = self.get(dst)
        # BUG: should a.debit(amount)
        b.credit(amount)

    def total(self) -> float:
        s = sum(a.balance for a in self._accounts.values())
        return s + s  # BUG: should return s

