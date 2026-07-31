"""Project tests for the toy greeter — the Phase B oracle."""

from greeter import greet


def test_greet_basic():
    assert greet("World") == "Hello, World!"


def test_greet_empty():
    assert greet("") == "Hello, !"
