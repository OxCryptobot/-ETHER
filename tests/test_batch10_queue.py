"""Batch 10 item 0 (2026-11-26): the host sat idle from 2026-11-24 21:14Z with 95 open real goals.

Evidence (origin main 3eb62be522 artifacts): 18 of the last 25 recorded attempts were
'gate aborted: baseline timeout' at 182-193 s (ETHER_GATE_TIMEOUT_S=180), each one spent a try
via gs.mark(kept=False), every open goal reached MAX_TRIES / MAX_TARGET_TRIES, next_real
returned None, host_main said next_goal 'none' + 'goal queue empty' while real_queue.open = 95.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest


def _repo(tmp_path: Path) -> Path:
    files = {
        "pkg/__init__.py": "",
        "pkg/m.py": "def f():\n    return 1\n",
        "tests/test_m.py": "from pkg.m import f\n\ndef test_f():\n    assert f() == 2\n",
        "tests/test_direct.py": "import pkg.m\n\ndef test_d():\n    assert True\n",
    }
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    (tmp_path / "artifacts").mkdir(exist_ok=True)
    return tmp_path


def _goal(i: int, via: str = "test_import") -> dict:
    return {"id": f"fix_{i}", "kind": "fix_test", "file": "pkg/m.py", "symbol": "f", "via": via,
            "nodeid": f"tests/test_m.py::t{i}", "test_file": "tests/test_m.py", "tractability": 0.5}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("ETHER_GATE_TIMEOUT_SCALE", "ETHER_GATE_TIMEOUT_MAX_S", "ETHER_GATE_TIMEOUT_MARGIN", "ETHER_ABORT_BACKOFF_S",
              "ETHER_ABORT_MAX", "ETHER_GOAL_RETRY_S", "ETHER_GOAL_MAX_ROUNDS", "ETHER_GUARD_TRIM", "ETHER_GOAL_LIVE_ONLY"):
        monkeypatch.delenv(k, raising=False)


def _timeout_run(calls):
    def run(root, args, timeout=None, sbfl=False, sandbox=None, aborts=0):
        calls.append({"args": list(args), "aborts": aborts})
        return {"ok": False, "rc": -9, "status": {}, "fail": {}, "secs": 181.0, "timeout": True, "timeout_s": 180}
    return run


def test_baseline_timeout_does_not_spend_tries(tmp_path, monkeypatch) -> None:
    from core.agent import goal_source as gs
    from core.agent import sota

    root = _repo(tmp_path)
    gs.save_index(root, {"goals": {"fix_0": _goal(0)}, "done": [], "dropped": {}, "cursor": 0})
    calls = []
    monkeypatch.setattr(gs, "run_pytest", _timeout_run(calls))
    monkeypatch.setattr(gs, "guard_suite", lambda r, g: ["tests/test_m.py", "tests/test_direct.py"] + [f"tests/x{i}.py" for i in range(8)])
    asked = []
    for n in range(1, 4):  # the host did exactly this to fix_test_pipeline_code_stage_failure on 11-24
        res = sota._attempt_real(root, lambda *a, **k: asked.append(1) or "", gs.load_index(root)["goals"]["fix_0"], None, {})
        assert res["gate_abort"] == "baseline timeout" and res["abort_n"] == n
    data = gs.load_index(root)
    assert int((data.get("tries") or {}).get("fix_0", 0)) == 0  # batch 9 burned all 3 tries here
    assert data["aborts"]["fix_0"]["n"] == 3 and not asked  # no model call was made
    # the next baseline is trimmed (direct guard kept) and asks for a longer timeout
    assert calls[0]["aborts"] == 0 and len(calls[0]["args"]) == 10
    assert calls[1]["aborts"] == 1 and len(calls[1]["args"]) == 2 + 4
    assert calls[2]["aborts"] == 2 and len(calls[2]["args"]) == 2 + 2
    # in backoff now, then selectable again
    assert gs.next_real(root) is None
    why = gs.why_blocked(root)
    assert why["blocked"] == {"abort_backoff": 1} and why["selectable"] == 0 and why["next_retry"]
    assert why["abort_reasons"] == {"baseline timeout": 1}
    monkeypatch.setenv("ETHER_ABORT_BACKOFF_S", "0")
    assert gs.next_real(root)["id"] == "fix_0"


def test_abort_parks_after_max_and_kept_clears(tmp_path, monkeypatch) -> None:
    from core.agent import goal_source as gs

    root = _repo(tmp_path)
    gs.save_index(root, {"goals": {"fix_0": _goal(0), "fix_1": _goal(1)}, "done": [], "dropped": {}, "cursor": 0})
    monkeypatch.setenv("ETHER_ABORT_BACKOFF_S", "0")
    monkeypatch.setenv("ETHER_ABORT_MAX", "2")
    gs.mark_abort(root, "fix_0", "baseline timeout")
    gs.mark_abort(root, "fix_0", "baseline timeout")
    assert gs.why_blocked(root)["blocked"] == {"abort_parked": 1}
    assert gs.next_real(root)["id"] == "fix_1"
    gs.mark_abort(root, "fix_1", "sandbox error: x")
    gs.mark(root, "fix_1", kept=True)
    assert "fix_1" not in gs.load_index(root)["aborts"]


def test_gate_abort_is_not_a_model_outcome() -> None:
    from core.agent.outcome import classify

    assert classify({"ok": False, "kind": "fix_test", "note": "gate aborted: baseline timeout",
                     "gate_abort": "baseline timeout"}) == "no_attempt"
    # an after-run timeout follows a model edit: still graded
    assert classify({"ok": False, "kind": "fix_test", "note": "gate aborted: after-run timeout"}) == "fail"


def test_untimed_exhausted_goals_are_readmitted_once(tmp_path, monkeypatch) -> None:
    """The live index: tries without timestamps (pre-batch-10, many were baseline aborts)."""
    from core.agent import goal_source as gs

    root = _repo(tmp_path)
    goals = {f"fix_{i}": _goal(i) for i in range(3)}
    gs.save_index(root, {"goals": goals, "done": [], "dropped": {}, "cursor": 0,
                         "tries": {g: 3 for g in goals}})
    assert gs.why_blocked(root)["blocked"] == {"exhausted": 3}
    g = gs.next_real(root)
    assert g is not None
    data = gs.load_index(root)
    assert data["tries"] == {g: 0 for g in goals} and data["rounds"] == {g: 1 for g in goals}
    assert data["tries_hist"] == {g: 3 for g in goals} and data["readmitted"]["n"] == 3
    # exhausted again now -> cooldown with timestamp, then a second round after ETHER_GOAL_RETRY_S x 2
    for gid in goals:
        for _ in range(3):
            gs.mark(root, gid, kept=False)
    assert gs.next_real(root) is None
    why = gs.why_blocked(root)
    assert why["blocked"] == {"exhausted": 3} and why["selectable"] == 0 and why["next_retry"]
    later = time.time() + 2 * 172800 + 10
    assert sorted(gs.readmit(root, now=later)) == sorted(goals)
    for gid in goals:
        for _ in range(3):
            gs.mark(root, gid, kept=False)
    assert gs.readmit(root, now=later + 10 * 172800) == []  # ETHER_GOAL_MAX_ROUNDS = 2
    monkeypatch.setenv("ETHER_GOAL_MAX_ROUNDS", "3")
    assert len(gs.readmit(root, now=later + 10 * 172800)) == 3


def test_retry_off_keeps_batch9_behaviour(tmp_path, monkeypatch) -> None:
    from core.agent import goal_source as gs

    root = _repo(tmp_path)
    gs.save_index(root, {"goals": {"fix_0": _goal(0)}, "done": [], "dropped": {}, "cursor": 0, "tries": {"fix_0": 3}})
    monkeypatch.setenv("ETHER_GOAL_RETRY_S", "0")
    assert gs.next_real(root) is None and gs.readmit(root) == []


def test_sbfl_cluster_is_readmitted(tmp_path) -> None:
    from core.agent import goal_source as gs

    root = _repo(tmp_path)
    goals = {f"fix_{i}": _goal(i, via="sbfl") for i in range(4)}
    gs.save_index(root, {"goals": goals, "done": [], "dropped": {}, "cursor": 0,
                         "tries": {"fix_0": 2, "fix_1": 2, "fix_2": 2}})
    assert gs.next_real(root) is not None  # untimed cluster tries -> re-admitted
    assert gs.load_index(root)["tries"] == {"fix_0": 0, "fix_1": 0, "fix_2": 0}


def test_gate_timeout_follows_measured_time(tmp_path, monkeypatch) -> None:
    from core.agent import goal_source as gs

    root = _repo(tmp_path)
    assert gs.gate_timeout(root, 16) == gs.GATE_TIMEOUT_S  # nothing measured yet
    gs.record_timing(root, 8, 54.7)  # the host's own scan: 8 files in 54.7 s
    assert gs.load_timing(root)["secs_per_file"] == pytest.approx(6.838, abs=1e-3)
    assert gs.gate_timeout(root, 16) == round(2 * 6.8375 * 16)  # 219 s > 180 s
    assert gs.gate_timeout(root, 16, aborts=1) == round(2 * 6.8375 * 16 * 1.5)
    gs.record_timing(root, 16, 180.0, timed_out=True)  # a timeout only raises the estimate
    assert gs.load_timing(root)["secs_per_file"] == pytest.approx(180 / 16 * 1.25, abs=1e-3)
    assert gs.gate_timeout(root, 400) == 900  # ETHER_GATE_TIMEOUT_MAX_S
    monkeypatch.setenv("ETHER_GATE_TIMEOUT_SCALE", "0")
    assert gs.gate_timeout(root, 400) == gs.GATE_TIMEOUT_S


def test_run_pytest_uses_scaled_timeout_and_records(tmp_path, monkeypatch) -> None:
    from core.agent import gate_jail
    from core.agent import goal_source as gs

    root = _repo(tmp_path)
    gs.record_timing(root, 1, 100.0)
    seen = {}

    def fake(argv, cwd, env, timeout=None, writable=()):
        seen["timeout"] = timeout
        return gate_jail.Result(returncode=-9, timed_out=True, jail="none")

    monkeypatch.setattr(gate_jail, "run", fake)
    res = gs.run_pytest(root, ["tests/test_m.py", "tests/test_direct.py"], sandbox=False)
    assert seen["timeout"] == 400 and res["timeout"] and res["timeout_s"] == 400
    assert gs.load_timing(root)["timeouts"] == 1
    gs.run_pytest(root, ["tests"], sandbox=False)  # full suite: fixed base timeout, not per-file
    assert seen["timeout"] == gs.GATE_TIMEOUT_S


def test_trim_suite(tmp_path, monkeypatch) -> None:
    from core.agent import goal_source as gs

    root = _repo(tmp_path)
    suite = ["tests/test_m.py", "tests/test_direct.py"] + [f"tests/x{i}.py" for i in range(8)]
    g = _goal(0)
    assert gs.trim_suite(root, g, suite, 0) == suite
    assert gs.trim_suite(root, g, suite, 1) == suite[:2] + suite[2:6]
    assert gs.trim_suite(root, g, suite, 9) == suite[:2]
    monkeypatch.setenv("ETHER_GUARD_TRIM", "0")
    assert gs.trim_suite(root, g, suite, 3) == suite


def test_queue_signal_agrees_with_real_queue() -> None:
    from scripts.host_signals import host_signals, queue_detail

    live = {"next_goal": "none", "sota": {"note": "queue empty"},
            "real_queue": {"open": 95, "done": 3, "dropped": 28}}
    text = queue_detail(live)
    assert "95 open real goals" in text and "empty" not in text  # the host's own row today
    live["real_queue"].update({"selectable": 0, "blocked": {"exhausted": 60, "target_exhausted": 30, "abort_backoff": 5},
                               "next_retry": "2026-11-28T00:00:00+00:00", "abort_reasons": {"baseline timeout": 5}})
    sig = [s for s in host_signals(live) if s["name"] == "queue"][0]
    assert sig["detail"].startswith("95 open real goals, 0 selectable; skipped: exhausted 60, target_exhausted 30, abort_backoff 5")
    assert "next retry 2026-11-28" in sig["detail"] and "baseline timeout x5" in sig["detail"]
    assert queue_detail({"real_queue": {"open": 0}}).startswith("goal queue empty")
