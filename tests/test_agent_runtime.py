"""The runtime is the product. It edits a real file and the tests keep it."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.agent.runtime import next_goal, run


def test_the_runtime_picks_its_own_goal(tmp_path: Path) -> None:
    goal = next_goal(tmp_path)
    assert goal["id"] == "fits"
    assert goal["file"].endswith("context_budget.py")


def _without_fits(tmp_path: Path) -> tuple:
    src = Path("core/kernel/context_budget.py").read_text(encoding="utf-8")
    src = src.replace(
        "\ndef fits(text: str) -> bool:\n    return len(text or '') <= context_char_budget()\n",
        "",
    )
    assert "def fits(" not in src
    target = tmp_path / "core" / "kernel"
    target.mkdir(parents=True)
    (target / "context_budget.py").write_text(src, encoding="utf-8")
    return src, target / "context_budget.py"


def test_the_runtime_does_not_inject_its_own_stub(tmp_path: Path) -> None:
    """Batch 3: a no-op model edit used to be replaced by an injected `fits` body
    and counted as kept. Now nothing is written and nothing is kept."""
    src, path = _without_fits(tmp_path)

    def ask(prompt: str, n: int = 240) -> str:
        return json.dumps({
            "tool": "edit",
            "args": {"path": "core/kernel/context_budget.py", "old": src, "new": src},
        })

    row = run(tmp_path, ask)
    assert row["kept_n"] == 0 and row["ok"] is False
    assert path.read_text(encoding="utf-8") == src


def test_the_runtime_keeps_a_real_model_edit(tmp_path: Path) -> None:
    src, path = _without_fits(tmp_path)
    anchor = "def context_char_budget("
    assert anchor in src
    new = ("def fits(text: str) -> bool:\n    return len(text or '') <= context_char_budget()\n\n\n" + anchor)

    def ask(prompt: str, n: int = 240) -> str:
        return json.dumps({"tool": "edit", "args": {"path": "core/kernel/context_budget.py", "old": anchor, "new": new}})

    row = run(tmp_path, ask)
    assert row["honest"] is True
    assert "fits" in row["batch"]
    import re

    assert re.search(r"^def fits\(", path.read_text(encoding="utf-8"), re.M)


def test_the_runtime_refuses_protected_paths(tmp_path: Path) -> None:
    _without_fits(tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("X = 1\n", encoding="utf-8")

    def ask(prompt: str, n: int = 240) -> str:
        return json.dumps({"tool": "edit", "args": {"path": "tests/test_x.py", "old": "X = 1",
                                                    "new": "def fits(t):\n    return True"}})

    row = run(tmp_path, ask)
    assert row["kept_n"] == 0
    assert (tmp_path / "tests" / "test_x.py").read_text(encoding="utf-8") == "X = 1\n"
