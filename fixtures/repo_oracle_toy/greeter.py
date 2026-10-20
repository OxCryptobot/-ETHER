"""Toy package under test — intentional bug for Phase B oracle demos."""


def greet(name: str) -> str:
    # BUG: the greeting format is wrong
    return f"Hello {name}"
