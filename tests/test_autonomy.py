"""Autonomy helpers — no network, no sandbox."""

from __future__ import annotations

from core.autonomy import ensure_assert_objective


def test_ensure_assert_adds_nudge():
    obj = "def add(a,b):\n    return a+b\nprint(add(1,2))"
    out = ensure_assert_objective(obj)
    assert "assert" in out.lower()


def test_ensure_assert_keeps_existing():
    obj = "def add(a,b):\n    return a+b\nassert add(1,2)==3\n"
    out = ensure_assert_objective(obj)
    assert out.strip() == obj.strip()


def test_empty_gets_default_with_asserts():
    out = ensure_assert_objective("")
    assert "assert" in out.lower()
    assert "is_even" in out
