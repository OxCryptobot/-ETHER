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


def test_review_reads_and_cannot_write(tmp_path: Path) -> None:
    from core.agent.checker import review

    state = tmp_path / "artifacts"
    state.mkdir()
    (state / "sota.json").write_text('{"goals": ["fix_add", "fix_clamp"]}', encoding="utf-8")
    row = review(tmp_path, ["fix_add", "fix_clamp"])
    assert row["writes"] is False
    assert row["ok"] is True
