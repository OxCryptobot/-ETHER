"""Batch 9 item 9: security-gem pre-gate on the real-goal path (ETHER_GEM_PREGATE, default off), and the
gate-mirror prune never takes a mirror that is in use. Tmp repos and a scripted mock model only."""
from __future__ import annotations

import os
import time

import pytest

from tests.test_batch7_exemplars import B_GOOD, TESTS_B, _repo, _run_until

B_SHELL = ("def floor_at(value, floor):\n    import subprocess\n    subprocess.run(['true'])\n"
           "    return max(value, floor)\n")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("ETHER_SAMPLE_TEMP", "ETHER_DEDUP_REPLY", "ETHER_EXEMPLARS", "ETHER_BANDIT", "ETHER_SOTA_EXPLORE",
              "ETHER_REFACTOR", "ETHER_MULTI_EDIT", "ETHER_NEURO_ES", "ETHER_BANDIT_FACTORED", "ETHER_GUARD_SUITE",
              "ETHER_GEM_PREGATE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ETHER_REAL_PER_TICK", "1")
    monkeypatch.setenv("ETHER_BANDIT_ARMS", "default")


def test_pregate_is_pure_and_counts_only_additions():
    from core.agent.pillars import pregate, pregate_on

    assert pregate_on() is False  # default off
    assert pregate("import subprocess\n", "import subprocess\nx = 1\n")["ok"] is True  # already there: not added
    row = pregate("x = 1\n", "x = eval('1')\nimport socket\n")
    assert row["ok"] is False and row["added"] == ["eval/exec", "socket"] and row["gem"] == "black_tourmaline"
    assert pregate("", "result = evaluate(x)\nobj.exec_query()\n")["ok"] is True  # names, not calls


def test_default_off_lets_the_gate_decide(tmp_path):
    """Flag off: the shell-adding but test-passing reply reaches the gate (batch 8 behaviour)."""
    root = _repo(tmp_path)
    rows = _run_until(root, lambda p, n=240: B_SHELL, "floor_at", n=1)
    assert rows[0].get("ok") is True


def test_flag_on_blocks_before_the_gate_and_restores(tmp_path, monkeypatch):
    from core.agent import goal_source as gs

    monkeypatch.setenv("ETHER_GEM_PREGATE", "1")
    root = _repo(tmp_path)
    original = (root / "pkg/b.py").read_text(encoding="utf-8")
    calls = []
    real_gate = gs.gate
    monkeypatch.setattr(gs, "gate", lambda *a, **k: calls.append(1) or real_gate(*a, **k))
    replies = iter([B_SHELL, B_GOOD])
    first = _run_until(root, lambda p, n=240: next(replies), "floor_at", n=1)[0]
    assert first.get("ok") is False and "gem blocked: subprocess" in str(first.get("note")), first
    assert not calls  # no gate run was spent
    assert (root / "pkg/b.py").read_text(encoding="utf-8") == original
    second = _run_until(root, lambda p, n=240: next(replies), "floor_at", n=1)[0]
    assert second.get("ok") is True and calls  # the clean fix goes through the gate and is kept
    assert (root / "tests/test_b.py").read_text(encoding="utf-8") == TESTS_B


def test_prune_keeps_mirrors_in_use(tmp_path, monkeypatch):
    from core.agent import gate_sandbox as gsb

    base = tmp_path / "ether_gate"
    keep = base / "keep"
    keep.mkdir(parents=True)
    busy = [base / f"busy{i}" for i in range(gsb.MIRROR_KEEP + 3)]
    idle = [base / f"idle{i}" for i in range(3)]
    for d in busy + idle:
        d.mkdir()
    old = time.time() - 2 * gsb.MIRROR_BUSY_S
    for d in idle:
        os.utime(d, (old, old))
    gsb._prune(base, keep)
    assert all(d.exists() for d in busy) and keep.exists()
    assert not any(d.exists() for d in idle)
