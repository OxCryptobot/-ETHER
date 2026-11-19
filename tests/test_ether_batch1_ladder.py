"""Batch 1: the over-cap slice, the stuck ladder, exact search, and infra outages."""
from __future__ import annotations

import json
import shutil
import urllib.error
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _legacy_ladder(monkeypatch):
    """These tests pin the legacy ladder (retired by default in batch 2)."""
    monkeypatch.setenv("ETHER_SOTA_LEGACY", "1")
    monkeypatch.setenv("ETHER_GOAL_SOURCE", "0")

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("ctx", ["8192", "4096", "2048"])
def test_slice_is_never_over_the_cap(monkeypatch: pytest.MonkeyPatch, ctx: str) -> None:
    from core.kernel.context_budget import context_char_budget, is_over, slice_to_budget

    monkeypatch.setenv("ETHER_MODEL_CTX", ctx)
    sliced = slice_to_budget("x" * 10000)
    assert len(sliced) <= context_char_budget()
    assert is_over(sliced) is False


def test_slice_keeps_matching_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.kernel.context_budget import slice_to_budget

    monkeypatch.setenv("ETHER_MODEL_CTX", "2048")
    lines = [f"noise {i} " + "y" * 60 for i in range(200)]
    lines[150] = "def target_fn(): return 1"
    out = slice_to_budget("\n".join(lines), query="target_fn")
    assert out == "def target_fn(): return 1"


def test_slice_short_text_is_unchanged() -> None:
    from core.kernel.context_budget import slice_to_budget

    assert slice_to_budget("abc") == "abc"
    assert slice_to_budget("") == ""


def _ladder_root(tmp_path: Path) -> Path:
    """A copy of the published state where every rung up to find_clamp is done
    and find_clamp is skipped. This is the host state at 1c92acf."""
    (tmp_path / "artifacts").mkdir()
    shutil.copy(REPO / "tests" / "fixtures" / "sota_1c92acf.json", tmp_path / "artifacts" / "sota.json")
    kernel = tmp_path / "core" / "kernel"
    kernel.mkdir(parents=True)
    (tmp_path / "core" / "__init__.py").write_text("", encoding="utf-8")
    (kernel / "__init__.py").write_text("", encoding="utf-8")
    import re

    body = (REPO / "core" / "kernel" / "context_budget.py").read_text(encoding="utf-8")
    # The host's filler stubs (add_name, failing_test) must not pre-answer the rungs.
    body = re.sub(r"\n+def (add_name|failing_test)\(\)[^\n]*\n(    [^\n]*\n)+", "\n", body)
    (kernel / "context_budget.py").write_text(body, encoding="utf-8")
    # A decoy: a nested helper named add, like core/pipeline_slices_canary.py.
    (tmp_path / "core" / "aaa_canary.py").write_text(
        "def run():\n    def add(name, ok):\n        return None\n", encoding="utf-8"
    )
    return tmp_path


def test_next_goal_reaches_find_add_past_a_skipped_rung(tmp_path: Path) -> None:
    from core.agent.sota import load, next_goal

    root = _ladder_root(tmp_path)
    state = load(root)
    assert "find_clamp" in state["skipped"]
    goal = next_goal(root)
    assert goal is not None and goal["id"] == "find_add"


def test_search_is_exact_top_level_and_posix(tmp_path: Path) -> None:
    from core.agent.skills import search

    root = _ladder_root(tmp_path)
    (root / "core" / "zz.py").write_text("def add_lesson():\n    pass\n", encoding="utf-8")
    row = search(root, "add")
    assert row["hits"] == ["core/kernel/context_budget.py"]
    assert search(root, "def add")["hits"] == ["core/kernel/context_budget.py"]
    assert search(root, "def test_")["hits"] == []


def test_find_add_is_kept_in_the_tested_file(tmp_path: Path) -> None:
    from core.agent.sota import load, run

    root = _ladder_root(tmp_path)
    replies = iter([
        '{"tool":"search","args":{"query":"add"}}',
        "def add_name() -> str:\n    return 'add'\n",
    ])

    def ask(prompt: str, n: int = 240) -> str:
        return next(replies, "def add_name() -> str:\n    return 'add'\n")

    row = run(root, ask)
    assert "find_add" in row["batch"], row
    body = (root / "core" / "kernel" / "context_budget.py").read_text(encoding="utf-8")
    assert "def add_name" in body
    assert "add_name" not in (root / "core" / "aaa_canary.py").read_text(encoding="utf-8")
    assert "find_add" in load(root)["goals"]


def test_an_ollama_outage_does_not_skip_the_goal(tmp_path: Path) -> None:
    from core.agent.sota import load, run

    root = _ladder_root(tmp_path)

    def ask(prompt: str, n: int = 240) -> str:
        raise urllib.error.URLError("connection refused")

    row = run(root, ask)
    assert row["ok"] is False
    assert row.get("infra") is True
    state = load(root)
    assert "find_add" not in state.get("skipped", [])
    assert "find_add" not in state.get("goals", [])


def test_host_main_shows_the_goal_the_run_will_try() -> None:
    src = (REPO / "scripts" / "host_main.py").read_text(encoding="utf-8")
    assert "sota_next_goal(root)" in src
    assert "next_from(root, done)" not in src
