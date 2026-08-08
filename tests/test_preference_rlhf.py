"""Offline RLHF unit tests — preference pairs + strategy boosts."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import preference as pref


@pytest.fixture()
def isolated_pref(tmp_path, monkeypatch):
    """Point preference module paths at a temp tree."""
    mem = tmp_path / "memory" / "experience"
    art = tmp_path / "artifacts"
    mem.mkdir(parents=True)
    art.mkdir(parents=True)
    monkeypatch.setattr(pref, "ROOT", tmp_path)
    monkeypatch.setattr(pref, "STATS_PATH", mem / "strategy_stats.json")
    monkeypatch.setattr(pref, "PREF_PATH", mem / "preferences.jsonl")
    monkeypatch.setattr(pref, "ARTIFACTS_STATS", art / "strategy_stats.json")
    monkeypatch.setattr(pref, "ARTIFACTS_SUMMARY", art / "preference_summary.json")
    monkeypatch.setattr(pref, "ARTIFACTS_PREFS_MIRROR", art / "preferences_tail.jsonl")
    return tmp_path


def _write_sb(path: Path, rows: list) -> None:
    path.write_text(
        json.dumps({"results": rows, "passed": sum(1 for r in rows if r.get("ok")), "total": len(rows)}),
        encoding="utf-8",
    )


def test_record_pairs_and_stats(isolated_pref):
    sb = isolated_pref / "artifacts" / "scoreboard_demo.json"
    _write_sb(
        sb,
        [
            {"mutation": "a", "arm": "direct", "ok": True, "score": 1.0},
            {"mutation": "b", "arm": "direct", "ok": False, "score": 0.0, "reason": "max_steps"},
            {"mutation": "c", "arm": "bare", "ok": False, "score": 0.2, "reason": "assert"},
        ],
    )
    meta = pref.record_preferences_from_scoreboard(sb)
    assert meta["reason"] == "ok"
    assert meta["stats_updated"] is True
    assert meta["stored"] >= 1
    assert pref.STATS_PATH.exists()
    assert pref.ARTIFACTS_STATS.exists()
    assert pref.PREF_PATH.exists()
    lines = [json.loads(x) for x in pref.PREF_PATH.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert any(p.get("rlhf") == "offline_pair" for p in lines)
    assert all("docker" not in str(p.get("rejected", {})) for p in lines)


def test_infra_rejected_not_paired(isolated_pref):
    sb = isolated_pref / "artifacts" / "scoreboard_infra.json"
    _write_sb(
        sb,
        [
            {"mutation": "a", "arm": "direct", "ok": True, "score": 1.0},
            {"mutation": "b", "arm": "direct", "ok": False, "score": 0.0, "reason": "cannot connect to ollama"},
        ],
    )
    meta = pref.record_preferences_from_scoreboard(sb)
    # stats still update, but no pair against infra
    assert meta["stats_updated"] is True
    assert meta["stored"] == 0


def test_live_boost_moves_with_wins(isolated_pref):
    # seed stats: tool_runtime wins a lot
    stats = {
        "strategies": {
            "tool_runtime": {"n": 10, "wins": 9, "score_sum": 9.0},
            "agent_loop": {"n": 10, "wins": 1, "score_sum": 1.0},
        },
        "n_episodes": 2,
        "updated": None,
    }
    pref.save_strategy_stats(stats)
    b_tool = pref.live_strategy_boost("tool_runtime")
    b_agent = pref.live_strategy_boost("agent_loop")
    assert b_tool > b_agent
    # unknown stays near default prior
    b_unk = pref.live_strategy_boost("never_seen_arm")
    assert b_unk > 0


def test_dpo_rank_score_sign():
    # policy likes preferred more than ref → positive
    s = pref.dpo_rank_score(
        preferred_logprob=-1.0,
        rejected_logprob=-3.0,
        ref_preferred_logprob=-1.5,
        ref_rejected_logprob=-1.5,
        beta=0.1,
    )
    assert s > 0


def test_assert_preferences_healthy(isolated_pref):
    sb = isolated_pref / "artifacts" / "scoreboard_health.json"
    _write_sb(sb, [{"mutation": "x", "arm": "direct", "ok": True, "score": 1.0}])
    pref.record_preferences_from_scoreboard(sb)
    health = pref.assert_preferences_healthy()
    assert health["ok"] is True
    assert health["checks"]["artifacts_stats"] is True
    assert health["checks"]["artifacts_summary"] is True


def test_rlhf_tick_discovers(isolated_pref):
    sb = isolated_pref / "artifacts" / "scoreboard_tick.json"
    _write_sb(
        sb,
        [
            {"mutation": "m1", "arm": "direct", "ok": True, "score": 1.0},
            {"mutation": "m2", "arm": "direct", "ok": False, "score": 0.0},
        ],
    )
    out = pref.rlhf_tick()
    assert out["health"]["ok"] is True
    assert out["processed"]["total_stored"] >= 1
