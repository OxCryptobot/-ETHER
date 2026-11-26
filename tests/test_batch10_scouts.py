"""Batch 10 item 5e: goal-flow scouts (ETHER_GOAL_SCOUTS=1). CPU only, no model calls."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from core.agent import scouts


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("ETHER_GOAL_SCOUTS", "ETHER_SCOUT_PATTERN", "ETHER_SCOUT_MIN_SELECTABLE", "ETHER_SCOUT_EVERY_S",
              "ETHER_SCOUT_FILES", "ETHER_GOAL_LIVE_ONLY", "ETHER_ABORT_BACKOFF_S", "ETHER_GOAL_RETRY_S"):
        monkeypatch.delenv(k, raising=False)


def _g(i, via, tr=0.5, kind="fix_test"):
    return {"id": f"{via}_{i}", "via": via, "kind": kind, "file": "pkg/m.py", "symbol": f"f{i}", "tractability": tr,
            "nodeid": f"tests/test_m.py::t_{via}_{i}", "test_file": "tests/test_m.py"}


def test_interleave_prefers_test_import_without_starving_sbfl() -> None:
    rows = [_g(i, "sbfl", 0.9) for i in range(4)] + [_g(i, "test_import", 0.3) for i in range(4)] + \
           [_g(0, "lint", 0.95, kind="lint"), _g(0, "weird")]
    out = scouts.interleave(rows)
    assert sorted(g["id"] for g in out) == sorted(g["id"] for g in rows)
    assert [scouts.source(g) for g in out[:7]] == ["test_import", "test_import", "sbfl", "lint", "weird",
                                                   "test_import", "test_import"]
    assert [g["id"] for g in out if g["via"] == "sbfl"] == [f"sbfl_{i}" for i in range(4)]  # inner order kept
    assert out.index(next(g for g in out if g["via"] == "sbfl")) < 4  # SBFL gets a slot in the first cycle


def test_ranked_uses_scouts_only_when_enabled(tmp_path, monkeypatch) -> None:
    from core.agent import goal_source as gs

    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "m.py").write_text("def f0():\n    return 1\n", encoding="utf-8")
    goals = {g["id"]: g for g in [_g(0, "sbfl", 0.9), _g(1, "sbfl", 0.8), _g(0, "test_import", 0.2)]}
    gs.save_index(tmp_path, {"goals": goals, "done": [], "dropped": {}, "cursor": 0})
    assert [g["id"] for g in gs.ranked(tmp_path)] == ["sbfl_0", "sbfl_1", "test_import_0"]
    monkeypatch.setenv("ETHER_GOAL_SCOUTS", "1")
    assert [g["id"] for g in gs.ranked(tmp_path)] == ["test_import_0", "sbfl_0", "sbfl_1"]
    assert gs.next_real(tmp_path)["id"] == "test_import_0"


def _repo(tmp_path: Path) -> Path:
    files = {"pkg/__init__.py": "", "pkg/m.py": "def double(x):\n    return x * 3\n",
             "tests/test_m.py": "from pkg.m import double\n\ndef test_d():\n    assert double(2) == 4\n"}
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    (tmp_path / "artifacts").mkdir()
    return tmp_path


def test_refill_scans_when_low_with_cooldown_and_no_model(tmp_path, monkeypatch) -> None:
    from core.agent import goal_source as gs

    root = _repo(tmp_path)
    row = scouts.refill(root)
    assert row["ran"] and row["selectable_before"] == 0 and row["scan"]["failing"] == 1
    assert row["selectable"] >= 1 and gs.load_index(root).get("scout_ts")
    monkeypatch.setenv("ETHER_SCOUT_MIN_SELECTABLE", "5")
    assert scouts.refill(root)["why"] == "cooldown"
    assert scouts.refill(root, now=time.time() + 601)["ran"] is True
    monkeypatch.setenv("ETHER_SCOUT_MIN_SELECTABLE", "1")
    assert scouts.refill(root, now=time.time() + 5000)["why"] == "enough"


def test_sota_run_calls_refill_only_when_enabled(tmp_path, monkeypatch) -> None:
    from core.agent import sota

    root = _repo(tmp_path)
    monkeypatch.setenv("ETHER_GOAL_SCAN", "0")
    monkeypatch.setenv("ETHER_SOTA_LEGACY", "0")
    calls = []
    monkeypatch.setattr(scouts, "refill", lambda r: calls.append(1) or {"ran": False, "why": "enough"})
    sota.run(root, lambda p, n=240: "")
    assert calls == []
    monkeypatch.setenv("ETHER_GOAL_SCOUTS", "1")
    row = sota.run(root, lambda p, n=240: "")
    assert calls == [1] and row["scouts"] == {"ran": False, "why": "enough"}
