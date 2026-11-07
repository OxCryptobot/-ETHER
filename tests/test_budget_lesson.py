"""A prompt over the cap fails. One lesson per day is what the next prompt sees."""
from __future__ import annotations

from pathlib import Path

from core.kernel.context_budget import context_char_budget, fits


def test_over_the_cap_fails() -> None:
    cap = context_char_budget()
    assert fits("x" * cap) is True
    assert fits("x" * (cap + 1)) is False


def test_one_lesson_per_day(tmp_path: Path) -> None:
    from core.agent.sota import recall, remember

    remember(tmp_path, "fix_add", "tests passed", kept=True, file="core/kernel/context_budget.py")
    seen = recall(tmp_path)
    assert "fix_add" in seen
    assert len(seen) <= 300
