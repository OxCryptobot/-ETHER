"""Toy package under test — intentional bug for Phase B oracle demos."""


def greet(name: str) -> str:
    # BUG: missing comma / wrong format — tests expect "Hello, {name}!"
    return f"Hello {name}"
