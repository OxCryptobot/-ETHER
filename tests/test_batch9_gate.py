"""Batch 9 item 1: the test-weakening route around the honest gate is closed (audit W1, PoC).

Tmp repos and a scripted mock model only."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_batch7_exemplars import B_GOOD, B_WRONG, TESTS_B, _goal, _repo, _run_until

WEAKEN = json.dumps({"tool": "edit", "args": {"rel": "tests/test_b.py",
                                              "old": "assert floor_at(1, 5) == 5", "new": "assert True"}})


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("ETHER_SAMPLE_TEMP", "ETHER_DEDUP_REPLY", "ETHER_EXEMPLARS", "ETHER_BANDIT", "ETHER_SOTA_EXPLORE",
              "ETHER_REFACTOR", "ETHER_MULTI_EDIT", "ETHER_NEURO_ES", "ETHER_BANDIT_FACTORED", "ETHER_GUARD_SUITE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ETHER_REAL_PER_TICK", "1")
    monkeypatch.setenv("ETHER_BANDIT_ARMS", "default")


def test_audit_poc_react_tool_call_cannot_edit_tests(tmp_path):
    """The audit PoC: one react() call edited tests/test_t.py. Now the call is denied."""
    from core.agent.react import react

    t = tmp_path / "tests" / "test_t.py"
    t.parent.mkdir(parents=True)
    t.write_text("def test_t():\n    assert 1 == 2\n", encoding="utf-8")
    replies = iter([json.dumps({"tool": "edit", "args": {"rel": "tests/test_t.py", "old": "1 == 2", "new": "True"}}),
                    json.dumps({"tool": "test", "args": {"code": "import os\nopen('pwned.txt','w').write('x')\n"}}),
                    "def f():\n    return 1\n"])
    row = react(lambda p, n=240: next(replies), tmp_path, "fix it", turns=3)
    assert t.read_text(encoding="utf-8") == "def test_t():\n    assert 1 == 2\n"
    assert not (tmp_path / "pwned.txt").exists() and not (tmp_path / "sota_ws").exists()
    assert row["used"] is True


def test_model_callable_skills_are_read_only(tmp_path):
    from core.agent.skills import MODEL_SKILLS, call, route

    assert set(MODEL_SKILLS) == {"search", "read"}
    for name in ("edit", "test", "remember"):
        row = call(tmp_path, json.dumps({"tool": name, "args": {}}))
        assert row["ok"] is False and row["reason"].startswith("denied"), name
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("X = 1\n", encoding="utf-8")
    assert route(tmp_path, "edit", rel="tests/test_x.py", old="X = 1", new="X = 2")["reason"] == "protected path"
    assert (tmp_path / "tests" / "test_x.py").read_text(encoding="utf-8") == "X = 1\n"


def test_read_skill_is_repo_confined(tmp_path):
    from core.agent.skills import route

    (tmp_path / "repo").mkdir()
    (tmp_path / "secret.txt").write_text("s3cret", encoding="utf-8")
    (tmp_path / "repo" / ".git").mkdir()
    (tmp_path / "repo" / ".git" / "config").write_text("url = https://x-access-token:abc@github.com", encoding="utf-8")
    (tmp_path / "repo" / "a.py").write_text("A = 1\n", encoding="utf-8")
    root = tmp_path / "repo"
    assert route(root, "read", rel="../secret.txt")["ok"] is False
    assert route(root, "read", rel=".git/config")["ok"] is False
    assert route(root, "read", rel="a.py")["body"] == "A = 1\n"


def test_real_goal_tool_call_weakening_the_test_never_keeps(tmp_path):
    """End to end on the real-goal path: the model tries the PoC edit, then a wrong function."""
    root = _repo(tmp_path)
    replies = iter([WEAKEN, B_WRONG] * 8)
    rows = _run_until(root, lambda p, n=240: next(replies), "floor_at", n=3)
    assert not any(r.get("ok") for r in rows)
    assert (root / "tests/test_b.py").read_text(encoding="utf-8") == TESTS_B


def test_candidate_that_rewrites_its_test_while_gated_is_rejected_and_restored(tmp_path, monkeypatch):
    """Right answer plus a side effect on tests/: kept before batch 9 (gate ran in place)."""
    monkeypatch.setenv("ETHER_GATE_SANDBOX", "0")  # in place: the side effect lands in the real tree
    root = _repo(tmp_path)
    cheat = ("def floor_at(value, floor):\n    import pathlib\n"
             "    pathlib.Path(r'%s').write_text('def test_b():\\n    pass\\n')\n"
             "    return max(value, floor)\n") % str(root / "tests" / "test_b.py")
    rows = _run_until(root, lambda p, n=240: cheat, "floor_at", n=2)
    assert not any(r.get("ok") for r in rows), rows
    assert any(str(r.get("note", "")).startswith("rejected: touched tests/test_b.py") for r in rows), rows
    assert (root / "tests/test_b.py").read_text(encoding="utf-8") == TESTS_B
    assert "return value\n" in (root / "pkg/b.py").read_text(encoding="utf-8")


def test_any_write_outside_the_goal_file_is_rejected_and_every_path_restored(tmp_path, monkeypatch):
    """Whatever the route (a future tool, a hook), the gate checks the whole tree diff."""
    from core.agent import goal_source as gs

    root = _repo(tmp_path)
    real_apply = gs.apply_edit

    def apply_and_cheat(r, goal, edit):
        res = real_apply(r, goal, edit)
        (Path(r) / "tests/test_b.py").write_text("def test_b():\n    pass\n", encoding="utf-8")
        (Path(r) / "pkg/a.py").write_text("def clamp_low(x, lo):\n    return 0\n", encoding="utf-8")
        (Path(r) / "pkg/extra.py").write_text("X = 1\n", encoding="utf-8")
        return res

    monkeypatch.setattr(gs, "apply_edit", apply_and_cheat)
    a_before = (root / "pkg/a.py").read_text(encoding="utf-8")
    rows = _run_until(root, lambda p, n=240: B_GOOD, "floor_at", n=2)
    assert not any(r.get("ok") for r in rows), rows
    last = rows[-1]
    assert set(last["outside"]) >= {"tests/test_b.py", "pkg/a.py", "pkg/extra.py"}
    assert (root / "tests/test_b.py").read_text(encoding="utf-8") == TESTS_B
    assert (root / "pkg/a.py").read_text(encoding="utf-8") == a_before
    assert not (root / "pkg/extra.py").exists()
    assert "return value\n" in (root / "pkg/b.py").read_text(encoding="utf-8")


def test_an_honest_edit_is_still_kept(tmp_path):
    root = _repo(tmp_path)
    rows = _run_until(root, lambda p, n=240: B_GOOD, "floor_at", n=2)
    assert rows[-1]["ok"] is True and rows[-1]["regressions"] == 0
    assert "max(value, floor)" in (root / "pkg/b.py").read_text(encoding="utf-8")


def test_tree_guard_unit(tmp_path):
    from core.agent.tree_guard import TreeGuard

    (tmp_path / "a.py").write_text("A\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "t.py").write_text("T\n", encoding="utf-8")
    (tmp_path / "artifacts").mkdir()
    g = TreeGuard(tmp_path).begin()
    (tmp_path / "a.py").write_text("B\n", encoding="utf-8")
    (tmp_path / "tests" / "t.py").unlink()
    (tmp_path / "new.py").write_text("N\n", encoding="utf-8")
    (tmp_path / "artifacts" / "x.json").write_text("{}", encoding="utf-8")  # runtime state: ignored
    assert g.changed() == {"a.py": "modified", "tests/t.py": "deleted", "new.py": "added"}
    assert g.violations(["a.py"]) == ["new.py", "tests/t.py"]
    assert g.violations(["a.py", "tests/t.py", "new.py"]) == ["tests/t.py"]  # tests/ is never allowed
    g.restore()
    assert g.changed() == {}
    assert (tmp_path / "tests" / "t.py").read_text(encoding="utf-8") == "T\n"
