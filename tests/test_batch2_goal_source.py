"""Batch 2: real goals (failing tests), quality guard, regression guard, arms."""
from __future__ import annotations

from pathlib import Path

import pytest

BUGGY = (
    "def double(x):\n"
    "    if x < 0:\n"
    "        return x * 2\n"
    "    return x * 2 + 1\n"
    "\n\n"
    "def triple(x):\n"
    "    return x * 3\n"
)
TESTS = (
    "from pkg.m import double, triple\n\n\n"
    "def test_double():\n"
    "    assert double(2) == 4\n\n\n"
    "def test_negative():\n"
    "    assert double(-3) == -6\n\n\n"
    "def test_triple():\n"
    "    assert triple(2) == 6\n"
)
GOOD = "def double(x):\n    return x * 2\n"
CHEAT = "def double(x):\n    return 4\n"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ETHER_SOTA_LEGACY", "0")
    monkeypatch.setenv("ETHER_GOAL_SOURCE", "1")
    monkeypatch.setenv("ETHER_GOAL_SCAN", "1")
    monkeypatch.setenv("ETHER_SOTA_EXPLORE", "0")
    monkeypatch.delenv("ETHER_REFACTOR", raising=False)


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "m.py").write_text(BUGGY, encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_m.py").write_text(TESTS, encoding="utf-8")
    (tmp_path / "artifacts").mkdir()
    return tmp_path


def _scanned(tmp_path: Path):
    from core.agent import goal_source as gs

    root = _repo(tmp_path)
    row = gs.scan(root, n_files=10)
    return root, row, gs.next_real(root)


def test_a_failing_test_becomes_one_unspoiled_goal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from core.agent import goal_source as gs
    from core.agent.goal_quality import check

    root, row, goal = _scanned(tmp_path)
    assert row["failing"] == 1 and goal is not None
    assert goal["kind"] == "fix_test" and goal["file"] == "pkg/m.py" and goal["symbol"] == "double"
    assert goal["nodeid"] == "tests/test_m.py::test_double"
    for ctx in ("2048", "4096", "8192"):
        monkeypatch.setenv("ETHER_MODEL_CTX", ctx)
        from core.kernel.context_budget import context_char_budget

        prompt = gs.build_prompt(root, goal)
        assert len(prompt) <= context_char_budget()
        assert GOOD not in prompt  # the answer is not there
        assert check(goal, prompt, (root / goal["file"]).read_text(encoding="utf-8"))["ok"]


def test_the_right_fix_is_kept_with_zero_regressions(tmp_path: Path) -> None:
    from core.agent import sota

    root, _, _ = _scanned(tmp_path)
    row = sota.run(root, lambda prompt, n=240: GOOD)
    assert row["batch"] == ["fix_test_double"]
    assert "return x * 2\n" in (root / "pkg" / "m.py").read_text(encoding="utf-8")


def test_a_cheat_that_regresses_another_test_is_reverted(tmp_path: Path) -> None:
    from core.agent import sota

    root, _, _ = _scanned(tmp_path)
    row = sota.run(root, lambda prompt, n=240: CHEAT)
    assert row["kept_n"] == 0
    assert row.get("regressions", 0) >= 1 or row.get("note") == "regression"
    assert (root / "pkg" / "m.py").read_text(encoding="utf-8") == BUGGY


def test_a_junk_reply_edits_nothing(tmp_path: Path) -> None:
    from core.agent import sota

    root, _, _ = _scanned(tmp_path)
    row = sota.run(root, lambda prompt, n=240: "I think you should check the docs.")
    assert row["kept_n"] == 0
    assert (root / "pkg" / "m.py").read_text(encoding="utf-8") == BUGGY


def test_quality_guard_rejects_constant_and_spoiled_goals() -> None:
    from core.agent.goal_quality import check, constant_test, spoiled

    assert constant_test("from a import describe\ndef test_d():\n    assert describe() == 'attach'\n")
    assert constant_test("def test_n():\n    assert failing_test() == 'found'\n")
    assert not constant_test("def test_c():\n    assert clamp(5, 0, 3) == 3\n")
    assert spoiled("Write only this:\ndef add(a, b):\n    return a + b\n", "add")
    assert not spoiled("Error: add(2, 3) returned 6\nReply with def add(...)\n", "add")
    assert check({"id": "describe_attach", "test": "assert describe() == 'attach'"})["reasons"][:1] == ["filler"]
    assert "self_edit" in check({"id": "fix_x", "kind": "fix_test", "file": "core/agent/sota.py"})["reasons"]


def test_retired_ladder_and_describe_seeding_hand_out_nothing(tmp_path: Path) -> None:
    from core.agent import sota

    (tmp_path / "core" / "kernel").mkdir(parents=True)
    (tmp_path / "core" / "kernel" / "alpha.py").write_text("X = 1\n", encoding="utf-8")
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts" / "sota.json").write_text('{"goals": ["describe_beta"]}\n', encoding="utf-8")
    assert sota.next_goal(tmp_path) is None
    assert sota.seed_depth(tmp_path) == 0
    assert sota.lost_kept(tmp_path) == []


def test_real_goals_get_their_own_bandit_and_explore(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from core.agent import outcome

    monkeypatch.delenv("ETHER_SOTA_EXPLORE", raising=False)
    goal = {"kind": "fix_test", "error_kind": "AssertionError"}
    assert outcome.explore_enabled(goal) is True and outcome.explore_enabled() is False
    pick = outcome.choose(tmp_path, goal=goal)
    assert pick.kind == "fix_test"
    row = outcome.record(tmp_path, pick, {"ok": True, "tests_ok": True, "goal": "fix_x", "kind": "fix_test"})
    assert row["bucket"].startswith("fix_test:") and row["goal_kind"] == "fix_test"
    assert outcome.bandit_path(tmp_path, "fix_test").is_file()


def test_arm_behaviour_changes_the_context(tmp_path: Path) -> None:
    from core.agent import goal_source as gs
    from core.learning import arm_behaviour

    root, _, goal = _scanned(tmp_path)
    with_ctx = gs.build_prompt(root, goal, arm_behaviour("default"))
    no_ctx = gs.build_prompt(root, goal, arm_behaviour("no_context"))
    assert "pkg/m.py (current)" in with_ctx and "pkg/m.py (current)" not in no_ctx


def test_function_replace_keeps_the_rest_of_the_file(tmp_path: Path) -> None:
    from core.agent import goal_source as gs

    root = _repo(tmp_path)
    out = gs.apply_function(root, {"file": "pkg/m.py", "symbol": "double"}, GOOD)
    assert out["ok"]
    body = (root / "pkg" / "m.py").read_text(encoding="utf-8")
    assert "def triple" in body and body.count("def double") == 1
    assert gs.extract_function("```python\ndef double(x):\n    return x * 2\n```\nDone.", "double") == GOOD
