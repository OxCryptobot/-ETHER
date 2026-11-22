"""Batch 8: ETHER_SAMPLE_TEMP (temperature by try index), duplicate-reply measurement, ETHER_DEDUP_REPLY.
Tmp repos and a mock model only."""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_batch7_exemplars import B_BUG, B_GOOD, B_WRONG, _goal, _repo, _run_until


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("ETHER_SAMPLE_TEMP", "ETHER_DEDUP_REPLY", "ETHER_EXEMPLARS", "ETHER_BANDIT_ARMS", "ETHER_BANDIT",
              "ETHER_SOTA_EXPLORE", "ETHER_REFACTOR", "ETHER_MULTI_EDIT", "ETHER_NEURO_ES", "ETHER_BANDIT_FACTORED"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ETHER_REAL_PER_TICK", "1")
    monkeypatch.setenv("ETHER_BANDIT_ARMS", "default")  # one arm: retries are same-arm, as greedy repeats are


class Recorder:
    """Mock 4B that takes a temperature like the host's _code: wrong when greedy, right when sampled."""

    def __init__(self, good_when_sampled=True):
        self.calls = []
        self.good = good_when_sampled

    def __call__(self, prompt: str, n: int = 240, temperature: float = 0.0) -> str:
        self.calls.append(temperature)
        return B_GOOD if (self.good and temperature > 0) else B_WRONG


def test_schedule_parsing_and_defaults(monkeypatch):
    from core.agent import sampling as s

    assert s.schedule() == [] and s.temp_for(5) == 0.0 and not s.enabled()
    monkeypatch.setenv("ETHER_SAMPLE_TEMP", "0,0.7")
    assert s.schedule() == [0.0, 0.7] and s.temp_for(0) == 0.0 and s.temp_for(1) == 0.7 and s.temp_for(9) == 0.7
    monkeypatch.setenv("ETHER_SAMPLE_TEMP", "0,9")
    assert s.temp_for(1) == s.MAX_TEMP
    for bad in ("0", "0,0", "x,0.7", ""):
        monkeypatch.setenv("ETHER_SAMPLE_TEMP", bad)
        assert s.schedule() == []
    ask = lambda p, n=240: "x"  # noqa: E731
    assert s.with_temp(ask, 0.7) is ask  # cannot take a temperature: unchanged, never a TypeError


def test_flag_off_never_passes_a_temperature(tmp_path):
    from core.agent.outcome import trajectories

    root = _repo(tmp_path)
    ask = Recorder()
    rows = _run_until(root, ask, "floor_at", n=4)
    assert not any(r.get("ok") for r in rows)
    assert ask.calls and all(t == 0.0 for t in ask.calls)
    assert all(t.get("temp") == 0.0 for t in trajectories(root) if t.get("reward01") is not None)


def test_schedule_samples_only_after_the_first_attempt(tmp_path, monkeypatch):
    from core.agent.outcome import trajectories

    monkeypatch.setenv("ETHER_SAMPLE_TEMP", "0,0.7")
    root = _repo(tmp_path)
    gid = _goal(root, "floor_at")["id"]
    ask = Recorder()
    rows = _run_until(root, ask, "floor_at", n=4)
    assert [r.get("ok") for r in rows] == [False, True], rows
    assert ask.calls[0] == 0.0 and ask.calls[-1] == 0.7
    traj = [t for t in trajectories(root) if t.get("goal") == gid]
    assert [t["temp"] for t in traj] == [0.0, 0.7] and [t["reward01"] for t in traj] == [0, 1]
    assert rows[-1]["regressions"] == 0
    assert "return max(value, floor)" in (root / "pkg/b.py").read_text()


def test_ask_without_temperature_still_works_with_the_flag(tmp_path, monkeypatch):
    from core.agent.outcome import trajectories

    monkeypatch.setenv("ETHER_SAMPLE_TEMP", "0,0.7")
    root = _repo(tmp_path)
    rows = _run_until(root, lambda p, n=240: B_WRONG, "floor_at", n=3)
    assert not any(r.get("ok") for r in rows) and not any(r.get("error") for r in rows)
    assert all(t.get("temp") == 0.0 for t in trajectories(root) if t.get("reward01") is not None)


def test_duplicate_replies_are_measured(tmp_path):
    from core.agent.outcome import metrics, trajectories

    root = _repo(tmp_path)
    gid = _goal(root, "floor_at")["id"]
    _run_until(root, lambda p, n=240: B_WRONG, "floor_at", n=3)
    traj = [t for t in trajectories(root) if t.get("goal") == gid]
    assert len(traj) == 3 and len({t["reply_hash"] for t in traj}) == 1
    assert [t["dup"] for t in traj] == [False, True, True]
    assert metrics(root)["dup_share"] == round(2 / 3, 4)
    assert metrics(root)["by_temp"] == {"0.0": {"attempts": 3, "kept": 0}}


def test_dedup_reuses_the_gates_own_refusal_and_never_keeps(tmp_path, monkeypatch):
    from core.agent import goal_source as gs
    from core.agent.outcome import trajectories

    monkeypatch.setenv("ETHER_DEDUP_REPLY", "1")
    root = _repo(tmp_path)
    gid = _goal(root, "floor_at")["id"]
    calls = []
    real_gate = gs.gate

    def counting_gate(*a, **k):
        calls.append(1)
        return real_gate(*a, **k)

    monkeypatch.setattr(gs, "gate", counting_gate)
    rows = _run_until(root, lambda p, n=240: B_WRONG, "floor_at", n=3)
    assert len(calls) == 1  # only the first identical edit is gated
    assert [r.get("note") for r in rows] == ["tests failed", "duplicate reply", "duplicate reply"]
    traj = [t for t in trajectories(root) if t.get("goal") == gid]
    assert [t["reward01"] for t in traj] == [0, 0, 0] and traj[1].get("dedup_skipped_from_cache") is True
    assert (root / "pkg/b.py").read_text() == B_BUG


def test_dedup_still_gates_a_different_reply_and_a_changed_state(tmp_path, monkeypatch):
    from core.agent import goal_source as gs

    monkeypatch.setenv("ETHER_DEDUP_REPLY", "1")
    root = _repo(tmp_path)
    replies = iter([B_WRONG, B_GOOD])
    rows = _run_until(root, lambda p, n=240: next(replies), "floor_at", n=2)
    assert [r.get("ok") for r in rows] == [False, True]
    from core.agent import sampling as s

    assert s.file_hash("x", {"t": "fail"}) != s.file_hash("x", {"t": "pass"})  # baseline change = new state


def test_dedup_off_by_default_gates_every_reply(tmp_path, monkeypatch):
    from core.agent import goal_source as gs

    root = _repo(tmp_path)
    calls = []
    real_gate = gs.gate
    monkeypatch.setattr(gs, "gate", lambda *a, **k: (calls.append(1), real_gate(*a, **k))[1])
    _run_until(root, lambda p, n=240: B_WRONG, "floor_at", n=3)
    assert len(calls) == 3


def test_host_code_forwards_temperature(monkeypatch):
    import ast

    src = (Path(__file__).resolve().parents[1] / "scripts/host_main.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == "_code")
    assert [a.arg for a in fn.args.args] == ["prompt", "n", "temperature"]
    assert fn.args.defaults[-1].value == 0.0  # unchanged default: greedy
    call = next(n for n in ast.walk(fn) if isinstance(n, ast.Call))
    assert {k.arg for k in call.keywords} >= {"temperature", "edit", "n"}


def test_first_hour_report_prints_duplicates_and_temperature():
    import importlib.util

    spec = importlib.util.spec_from_file_location("fhr8", Path(__file__).resolve().parents[1] / "scripts/first_hour_report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ls = mod.learning_view({"schema": 2, "totals": {"graded": 4}, "bandit": {},
                            "metrics": {"dup_share": 0.5, "by_temp": {"0.0": {"attempts": 3, "kept": 0},
                                                                      "0.7": {"attempts": 1, "kept": 1}}}})
    text = mod.render({"ref": "x", "head": "h", "host": {"present": False}, "learning": ls,
                       "commits": {"n": 0, "per_hour": 0, "window_h": 1}})
    assert "duplicate replies 0.500  kept by temperature: T=0.0 0/3, T=0.7 1/1" in text
