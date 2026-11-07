"""The model writes the function. The tests keep it. Nothing is injected."""
from __future__ import annotations

import json
from pathlib import Path

from core.agent.sota import run


def test_the_model_writes_it(tmp_path: Path) -> None:
    src = Path("core/kernel/context_budget.py").read_text(encoding="utf-8")
    target = tmp_path / "core" / "kernel"
    target.mkdir(parents=True)
    (target / "context_budget.py").write_text(src, encoding="utf-8")

    def ask(prompt: str, n: int = 240) -> str:
        return "def packed_count(text: str) -> int:\n    return text.count('### ')\n"

    row = run(tmp_path, ask)
    assert "packed_count" in row["batch"]
    body = (target / "context_budget.py").read_text(encoding="utf-8")
    assert "def packed_count" in body


def test_a_non_function_is_not_kept(tmp_path: Path) -> None:
    src = Path("core/kernel/context_budget.py").read_text(encoding="utf-8")
    target = tmp_path / "core" / "kernel"
    target.mkdir(parents=True)
    (target / "context_budget.py").write_text(src, encoding="utf-8")

    def ask(prompt: str, n: int = 240) -> str:
        return "I am not sure"

    before = (target / "context_budget.py").read_text(encoding="utf-8")
    row = run(tmp_path, ask)
    assert row["ok"] is False
    assert (target / "context_budget.py").read_text(encoding="utf-8") == before
