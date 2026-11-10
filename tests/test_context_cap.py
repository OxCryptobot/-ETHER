"""A prompt over the cap fails."""
from __future__ import annotations

from core.kernel.context_budget import is_over, slice_to_budget


def test_over_cap_fails() -> None:
    big = "x" * 10000
    assert is_over(big) is True


def test_slice_fits() -> None:
    big = "x" * 10000
    sliced = slice_to_budget(big)
    assert is_over(sliced) is False
