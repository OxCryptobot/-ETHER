"""Batch 10 item 5: 1650-safe proposer swarm (ETHER_SWARM=1, default off).
One model, serialized calls; CPU workers screen; one writer; the honest gate is unchanged."""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from core.agent import swarm

BUGGY = "def double(x):\n    if x < 0:\n        return x * 2\n    return x * 2 + 1\n"
TESTS = ("from pkg.m import double\n\n\ndef test_double():\n    assert double(2) == 4\n\n\n"
         "def test_negative():\n    assert double(-3) == -6\n")
GOOD = "def double(x):\n    return x * 2\n"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("ETHER_SOTA_LEGACY", "0")
    monkeypatch.setenv("ETHER_GOAL_SOURCE", "1")
    monkeypatch.setenv("ETHER_GOAL_SCAN", "1")
    monkeypatch.setenv("ETHER_SOTA_EXPLORE", "0")
    for k in ("ETHER_REFACTOR", "ETHER_SWARM", "ETHER_SWARM_K", "ETHER_SWARM_TEMP", "ETHER_SAMPLE_TEMP", "ETHER_LSP",
              "ETHER_LSP_PREGATE", "ETHER_MCP"):
        monkeypatch.delenv(k, raising=False)


def _repo(tmp_path: Path) -> Path:
    for rel, text in {"pkg/__init__.py": "", "pkg/m.py": BUGGY, "tests/test_m.py": TESTS}.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    (tmp_path / "artifacts").mkdir()
    return tmp_path


def test_off_by_default_and_k_is_two() -> None:
    assert swarm.enabled() is False
    assert swarm.k() == 2  # SWARM_DESIGN phase B starts at best-of-2


def test_model_calls_never_overlap_and_screening_overlaps_generation(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ETHER_SWARM_K", "3")
    live = {"n": 0, "max": 0}
    events = []
    guard = threading.Lock()

    def ask(prompt, n=240, temperature=0.0):
        with guard:
            live["n"] += 1
            live["max"] = max(live["max"], live["n"])
        events.append(("gen_start", time.monotonic()))
        time.sleep(0.15)
        with guard:
            live["n"] -= 1
        return GOOD if temperature > 0 else "no code here"

    def slow_screen(root, goal, text, current, baseline):
        events.append(("screen_start", time.monotonic()))
        time.sleep(0.1)
        return {"ok": "def " in text, "why": "" if "def " in text else "no edit", "hash": str(hash(text) if "def " in text else "")}

    monkeypatch.setattr(swarm, "screen", slow_screen)
    root = _repo(tmp_path)
    goal = {"id": "g", "file": "pkg/m.py", "symbol": "double", "kind": "fix_test"}
    # many threads hammering the same ask through the lock: still one at a time
    calls = [threading.Thread(target=lambda: swarm.serialized(ask, root)("p")) for _ in range(4)]
    [t.start() for t in calls]
    [t.join() for t in calls]
    assert live["max"] == 1 and not (root / swarm.LOCK_FILE).exists()
    events.clear()
    out = swarm.propose(root, goal, ask, "p", 240, 0.0, BUGGY, {})
    assert out["text"] == GOOD and out["trace"]["k"] == 3 and out["trace"]["picked"] == 1
    assert out["trace"]["valid"] == 2 and out["trace"]["distinct"] == 1 and live["max"] == 1
    first_screen = min(t for e, t in events if e == "screen_start")
    last_gen = max(t for e, t in events if e == "gen_start")
    assert first_screen < last_gen  # CPU worker ran while the model generated the next candidate


def test_no_temperature_means_one_candidate(tmp_path) -> None:
    root = _repo(tmp_path)
    calls = []

    def ask(prompt, n=240):  # cannot sample: K identical replies would waste the GPU
        calls.append(1)
        return GOOD

    out = swarm.propose(root, {"id": "g", "file": "pkg/m.py", "symbol": "double", "kind": "fix_test"},
                        ask, "p", 240, 0.0, BUGGY, {})
    assert out["trace"]["k"] == 1 and len(calls) == 1 and out["text"] == GOOD


def test_screen_is_read_only_and_rejects_bad_replies(tmp_path) -> None:
    root = _repo(tmp_path)
    goal = {"id": "g", "file": "pkg/m.py", "symbol": "double", "kind": "fix_test"}
    assert swarm.screen(root, goal, GOOD, BUGGY, {})["ok"]
    assert swarm.screen(root, goal, "nothing", BUGGY, {})["why"] == "no edit"
    bad = swarm.screen(root, goal, "def double(x):\n    return (\n", BUGGY, {})
    assert not bad["ok"]
    gem = swarm.screen(root, goal, "def double(x):\n    import os\n    os.system('x')\n    return x * 2\n", BUGGY, {})
    assert (root / "pkg" / "m.py").read_text(encoding="utf-8") == BUGGY
    assert gem["ok"] in (True, False)


def test_stale_lock_is_broken(tmp_path) -> None:
    import os

    lock = tmp_path / swarm.LOCK_FILE
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("999999")
    old = time.time() - 7200
    os.utime(lock, (old, old))
    with swarm.model_lock(tmp_path):
        assert lock.exists()
    assert not lock.exists()
    lock.write_text("1")
    with pytest.raises(TimeoutError):
        with swarm.model_lock(tmp_path, timeout_s=0.3):
            pass


def test_end_to_end_swarm_finds_the_fix_the_greedy_reply_missed(tmp_path, monkeypatch) -> None:
    from core.agent import goal_source as gs
    from core.agent import sota

    root = _repo(tmp_path)
    gs.scan(root, n_files=10)

    def ask(prompt, n=240, temperature=0.0):
        return GOOD if temperature > 0 else "I am not sure."

    row = sota.run(root, ask)
    assert row["kept_n"] == 0  # swarm off: greedy reply only, nothing kept
    data = gs.load_index(root)
    data["tries"] = {}
    gs.save_index(root, data)
    monkeypatch.setenv("ETHER_SWARM", "1")
    row = sota.run(root, ask)
    assert row["kept_n"] == 1 and row.get("regressions", 0) == 0
    assert "return x * 2\n" in (root / "pkg" / "m.py").read_text(encoding="utf-8")
