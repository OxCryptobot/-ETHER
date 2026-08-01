"""Toy wallet package — intentional bugs for Phase B oracle task set.

BUGS:
- deposit always overwrites balance instead of adding
- withdraw never checks insufficient funds
"""


class Wallet:
    def __init__(self, balance: float = 0.0) -> None:
        self.balance = float(balance)

    def deposit(self, amount: float) -> float:
        if amount < 0:
            raise ValueError("amount must be non-negative")
        # BUG: overwrites instead of adding
        self.balance = amount
        return self.balance

    def withdraw(self, amount: float) -> float:
        if amount < 0:
            raise ValueError("amount must be non-negative")
        # BUG: missing insufficient-funds check
        self.balance = self.balance - amount
        return self.balance
