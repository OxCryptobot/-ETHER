"""The runtime is the product. It edits a real file and the tests keep it."""
from __future__ import annotations

import json
from pathlib import Path

from core.agent.runtime import next_goal, run


def test_the_runtime_picks_its_own_goal(tmp_path: Path) -> None:
    goal = next_goal(tmp_path)
    assert goal["id"] == "fits"
    assert goal["file"].endswith("context_budget.py")


def test_the_runtime_edits_a_real_file(tmp_path: Path) -> None:
    src = Path("core/kernel/context_budget.py").read_text(encoding="utf-8")
    src = src.replace(
        "\ndef fits(text: str) -> bool:\n    return len(text or '') <= context_char_budget()\n",
        "",
    )
    target = tmp_path / "core" / "kernel"
    target.mkdir(parents=True)
    (target / "context_budget.py").write_text(src, encoding="utf-8")

    def ask(prompt: str, n: int = 240) -> str:
        return json.dumps({
            "tool": "edit",
            "args": {"path": "core/kernel/context_budget.py", "old": src, "new": src},
        })

    row = run(tmp_path, ask)
    assert row["honest"] is True
    assert row["tx"] == ["begin", "promote"]
    assert "def fits" in (target / "context_budget.py").read_text(encoding="utf-8")
