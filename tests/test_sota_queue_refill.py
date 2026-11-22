"""SOTA queue: a failed rung must not stall the ladder; kept-but-missing edits are requeued."""
from __future__ import annotations

import pytest

import json
from pathlib import Path

from core.agent.sota import lost_kept, next_goal



@pytest.fixture(autouse=True)
def _legacy_ladder(monkeypatch):
    """These tests pin the legacy ladder (retired by default in batch 2)."""
    monkeypatch.setenv("ETHER_SOTA_LEGACY", "1")
    monkeypatch.setenv("ETHER_GOAL_SOURCE", "0")

def _repo(tmp_path: Path, state: dict, budget: str, kernel: dict | None = None) -> Path:
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts" / "sota.json").write_text(json.dumps(state), encoding="utf-8")
    k = tmp_path / "core" / "kernel"
    k.mkdir(parents=True)
    (k / "context_budget.py").write_text(budget, encoding="utf-8")
    for name, body in (kernel or {}).items():
        (k / f"{name}.py").write_text(body, encoding="utf-8")
    return tmp_path


FIXED = ["packed_count", "fits_empty", "file_count", "is_over", "budget_of"]
LADDER_DONE = ["same_count", "within_budget", "count_diff", "room_left", "find_fits", "budget_status",
               "fix_add", "fix_clamp"]
BUDGET = "".join(f"def {s}(*a):\n    return 0\n\n" for s in
                 ["packed_count", "fits", "file_count", "is_over", "budget_of", "same_count", "within_budget",
                  "count_diff", "room_left", "fits_name", "budget_status", "add", "clamp"])


def test_failed_rung_does_not_stall_ladder(tmp_path: Path) -> None:
    """Origin state on 2026-11-19: find_clamp skipped -> queue was 'empty' while find_add was open."""
    root = _repo(tmp_path, {"goals": FIXED + LADDER_DONE, "skipped": ["find_clamp"], "lessons": []}, BUDGET)
    goal = next_goal(root)
    assert goal is not None and goal["id"] == "find_add"


def test_kept_but_missing_edit_is_requeued(tmp_path: Path) -> None:
    state = {"goals": FIXED + LADDER_DONE + ["find_add", "next_bug", "describe_alpha", "describe_beta"],
             "skipped": ["find_clamp"], "lessons": []}
    budget = BUDGET + "def add_name():\n    return 'add'\n\ndef failing_test():\n    return 'found'\n"
    root = _repo(tmp_path, state, budget, {
        "alpha": "def describe() -> str:\n    return 'alpha'\n",
        "beta": "X = 1\n",  # kept in sota.json, but the edit never landed
    })
    assert lost_kept(root) == ["describe_beta"]
    goal = next_goal(root)
    assert goal is not None and goal["id"] == "describe_beta"
    assert goal["requeued"] == "lost_kept"
    assert "assert describe() == 'beta'" in goal["test"]  # the honest gate still decides


def test_requeued_goal_that_fails_again_is_not_retried(tmp_path: Path) -> None:
    state = {"goals": FIXED + LADDER_DONE + ["find_add", "next_bug", "describe_beta", "describe_context_budget"],
             "skipped": ["find_clamp", "describe_beta"], "lessons": []}
    budget = BUDGET + "def add_name():\n    return 'add'\n\ndef failing_test():\n    return 'found'\n" \
        + "def describe():\n    return 'context_budget'\n"
    root = _repo(tmp_path, state, budget, {"beta": "X = 1\n", "gamma": "def describe():\n    return 'gamma'\n"})
    assert next_goal(root) is None


def test_host_main_reports_the_goal_the_batch_will_try() -> None:
    text = Path("scripts/host_main.py").read_text(encoding="utf-8")
    learn = text.split("def _learn(", 1)[1].split("def tick(", 1)[0]
    assert "sota_next_goal(root)" in learn and "next_from(" not in learn


def test_ladder_generator_seeds_other_packages_after_kernel(tmp_path: Path) -> None:
    state = {"goals": FIXED + LADDER_DONE + ["find_add", "next_bug", "describe_context_budget"],
             "skipped": ["find_clamp"], "lessons": []}
    budget = BUDGET + "def add_name():\n    return 'add'\n\ndef failing_test():\n    return 'found'\n" \
        + "def describe():\n    return 'context_budget'\n"
    root = _repo(tmp_path, state, budget)
    loop = tmp_path / "core" / "loop"
    loop.mkdir()
    (loop / "worktree.py").write_text("X = 1\n", encoding="utf-8")
    agent = tmp_path / "core" / "agent"
    agent.mkdir()
    (agent / "sota.py").write_text("X = 1\n", encoding="utf-8")
    from core.agent.sota import seed_depth

    assert seed_depth(root) == 1  # core/agent (the writer's brain) is never seeded
    goal = next_goal(root)
    assert goal["id"] == "describe_loop_worktree"  # no collision with kernel describe_worktree
    assert goal["file"] == "core/loop/worktree.py"
    assert "from core.loop.worktree import describe" in goal["test"]
