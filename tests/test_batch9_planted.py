"""Batch 9 item 5: planted-bug goals (ETHER_PLANTED_GOALS, default off) and live-only goals."""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

GOOD = "def add_one(x):\n    return x + 1\n"
WRONG = "def add_one(x):\n    return x\n"


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path_factory):
    for k in ("ETHER_PLANTED_GOALS", "ETHER_GOAL_LIVE_ONLY", "ETHER_EXEMPLARS", "ETHER_SAMPLE_TEMP", "ETHER_DEDUP_REPLY",
              "ETHER_BANDIT", "ETHER_SOTA_EXPLORE", "ETHER_MULTI_EDIT", "ETHER_REFACTOR", "ETHER_BANDIT_FACTORED"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ETHER_BANDIT_ARMS", "default")
    monkeypatch.setenv("ETHER_PLANTED_DIR", str(tmp_path_factory.mktemp("planted")))
    monkeypatch.setenv("ETHER_GATE_SANDBOX_DIR", str(tmp_path_factory.mktemp("gate")))


def _repo(tmp_path: Path) -> Path:
    files = {
        "scripts/__init__.py": "",
        "scripts/host_main.py": "from pkg.live import add_one\n",
        "pkg/__init__.py": "",
        "pkg/live.py": GOOD,
        "pkg/dead.py": "def unused(x):\n    return x - 1\n",
        "tests/test_live.py": "from pkg.live import add_one\n\n\ndef test_add_one():\n    assert add_one(1) == 2\n",
        "tests/test_dead.py": "from pkg.dead import unused\n\n\ndef test_unused():\n    assert unused(3) == 2\n",
    }
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    (tmp_path / "artifacts").mkdir()
    return tmp_path


def test_live_files_follow_the_writer_imports(tmp_path):
    from core.agent import planted

    root = _repo(tmp_path)
    live = planted.live_files(root)
    assert "pkg/live.py" in live and "pkg/dead.py" not in live


def test_generate_validates_a_bug_on_live_code_and_never_touches_the_tree(tmp_path):
    from core.agent import planted
    from core.agent.tree_guard import TreeGuard

    root = _repo(tmp_path)
    guard = TreeGuard(root).begin()
    made = planted.generate(root, n=3, rng=random.Random(1))
    assert made, "no validated planted bug"
    g = made[0]
    assert g["file"] == "pkg/live.py" and g["planted"] is True and g["nodeid"] == "tests/test_live.py::test_add_one"
    assert g["kind"] == "fix_test" and g["site"]["op"] in ("arith", "const")
    assert guard.changed() == {}  # the writer tree is never mutated
    pool = json.loads((root / "memory/planted/pool.json").read_text(encoding="utf-8"))
    assert g["id"] in pool["goals"]


def test_equivalent_mutants_are_rejected(tmp_path):
    from core.agent import planted

    root = _repo(tmp_path)
    (root / "pkg/live.py").write_text("def add_one(x):\n    if x < -100:\n        return x + 1\n    return x + 1\n",
                                      encoding="utf-8")
    src = (root / "pkg/live.py").read_text(encoding="utf-8")
    fn = planted._functions(src)[0]
    cmp_site = [s for s in planted.sites(src, fn) if s["op"] == "compare"]
    assert cmp_site and planted.mutate(src, cmp_site[0]).count("<=") == 1
    for _ in range(4):
        planted.generate(root, n=5, rng=random.Random(_))
    pool = planted.load_pool(root)
    assert all(g["site"]["op"] != "compare" for g in pool["goals"].values())  # < vs <= at -100: not killed


def test_planted_attempt_runs_the_honest_gate_in_scratch_and_learns(tmp_path, monkeypatch):
    from core.agent import planted, sota
    from core.agent.outcome import trajectories
    from core.agent.tree_guard import TreeGuard

    monkeypatch.setenv("ETHER_PLANTED_GOALS", "1")
    root = _repo(tmp_path)
    guard = TreeGuard(root).begin()
    monkeypatch.setattr(sota, "next_goal", lambda r, skip=(): None)
    row = sota._one(root, lambda p, n=240: GOOD)
    assert row["planted"] is True and row["ok"] is True and row["regressions"] == 0, row
    assert guard.changed() == {}
    assert not (root / "artifacts/goal_index.json").exists()  # real index untouched
    sota_state = root / "artifacts/sota.json"
    assert not sota_state.exists() or "pkg/live.py" not in json.loads(sota_state.read_text())["files"]
    traj = [t for t in trajectories(root) if str(t.get("goal", "")).startswith("planted_")]
    assert traj and traj[-1]["reward01"] == 1
    pool = planted.load_pool(root)
    assert row["goal"] in pool["done"]


def test_wrong_fixes_are_tried_then_dropped(tmp_path, monkeypatch):
    from core.agent import planted, sota

    monkeypatch.setenv("ETHER_PLANTED_GOALS", "1")
    root = _repo(tmp_path)
    monkeypatch.setattr(sota, "next_goal", lambda r, skip=(): None)
    first = sota._one(root, lambda p, n=240: WRONG)
    assert first["planted"] is True and first["ok"] is False
    gid = first["goal"]
    for _ in range(planted.MAX_TRIES - 1):
        sota._one(root, lambda p, n=240: WRONG)
    assert gid not in planted.load_pool(root)["goals"] or planted.load_pool(root)["tries"][gid] >= planted.MAX_TRIES
    assert (root / "pkg/live.py").read_text(encoding="utf-8") == GOOD


def test_flag_off_leaves_an_empty_queue_empty(tmp_path, monkeypatch):
    from core.agent import sota

    root = _repo(tmp_path)
    monkeypatch.setattr(sota, "next_goal", lambda r, skip=(): None)
    row = sota._one(root, lambda p, n=240: GOOD)
    assert row["note"] == "queue empty" and not (root / "memory/planted").exists()


def test_live_only_drops_goals_on_dead_code(tmp_path, monkeypatch):
    from core.agent import goal_source as gs

    root = _repo(tmp_path)
    data = {"goals": {
        "g_live": {"id": "g_live", "kind": "fix_test", "file": "pkg/live.py", "symbol": "add_one", "tractability": 0.5},
        "g_dead": {"id": "g_dead", "kind": "fix_test", "file": "pkg/dead.py", "symbol": "unused", "tractability": 0.9},
    }, "done": [], "dropped": {}, "cursor": 0}
    gs.save_index(root, data)
    assert [g["id"] for g in gs.ranked(root)] == ["g_dead", "g_live"]
    monkeypatch.setenv("ETHER_GOAL_LIVE_ONLY", "1")
    assert [g["id"] for g in gs.ranked(root)] == ["g_live"]


def test_scratch_is_outside_the_repo(tmp_path, monkeypatch):
    from core.agent import planted

    monkeypatch.setenv("ETHER_PLANTED_DIR", str(tmp_path / "inside"))
    with pytest.raises(ValueError):
        planted.scratch_dir(tmp_path)


def test_goal_seed_skips_dead_code_when_live_only(tmp_path, monkeypatch):
    from scripts.goal_seed import build

    root = _repo(tmp_path)
    (root / "pkg/live.py").write_text(WRONG, encoding="utf-8")
    (root / "pkg/dead.py").write_text("def unused(x):\n    return x\n", encoding="utf-8")
    xml = tmp_path / "t.xml"
    xml.write_text('''<testsuites><testsuite>
<testcase classname="tests.test_live" name="test_add_one"><failure message="assert 1 == 2">tests/test_live.py:5: AssertionError</failure></testcase>
<testcase classname="tests.test_dead" name="test_unused"><failure message="assert 3 == 2">tests/test_dead.py:5: AssertionError</failure></testcase>
</testsuite></testsuites>''', encoding="utf-8")
    both = build(root, xml)
    monkeypatch.setenv("ETHER_GOAL_LIVE_ONLY", "1")
    live = build(root, xml)
    files = lambda d: sorted(g["file"] for g in d["goals"].values() if g["kind"] == "fix_test")  # noqa: E731
    assert "pkg/dead.py" in files(both) and files(live) == [f for f in files(both) if f != "pkg/dead.py"]
    assert live["dropped"].get("tests/test_dead.py::test_unused") == "dead_code"
