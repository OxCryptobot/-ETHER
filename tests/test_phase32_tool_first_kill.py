"""Phase 3.2 — tool-first adapter identity + kill script hygiene."""
from __future__ import annotations

from pathlib import Path

from core.pipeline_tool_first import decide_pipeline_tool_first
from scripts.kill_live_pending import main as kill_main


def test_tool_first_fail_matches_pipeline_contract():
    d = decide_pipeline_tool_first(
        tool_runtime_enabled=True,
        tool_runtime_done=False,
        error="max_steps",
    )
    assert d.should_fail is True
    assert d.degrade_marker == "tool_runtime_failed_terminal"
    assert d.fail_stage == "tool_runtime"
    assert d.fail_msg == "tool_runtime_failed_terminal"


def test_tool_first_done_does_not_fail():
    d = decide_pipeline_tool_first(
        tool_runtime_enabled=True,
        tool_runtime_done=True,
        score=1.0,
    )
    assert d.should_fail is False
    assert d.degrade_marker is None


def test_tool_first_disabled_continues():
    d = decide_pipeline_tool_first(
        tool_runtime_enabled=False,
        tool_runtime_done=False,
    )
    assert d.should_fail is False


def test_kill_live_pending_moves_matching(tmp_path, monkeypatch):
    pending = tmp_path / "artifacts" / "jobs" / "pending"
    arch = tmp_path / "artifacts" / "jobs" / "failed_archived"
    pending.mkdir(parents=True)
    (pending / "ss_pipeline_ledger_x.json").write_text("{}", encoding="utf-8")
    (pending / "keep_me.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr("scripts.kill_live_pending.ROOT", tmp_path)
    monkeypatch.setattr("scripts.kill_live_pending.PENDING", pending)
    monkeypatch.setattr("scripts.kill_live_pending.ARCH", arch)
    assert kill_main() == 0
    assert not (pending / "ss_pipeline_ledger_x.json").exists()
    assert (pending / "keep_me.json").exists()
    assert any(arch.glob("ss_pipeline_ledger_x_killed_*.json"))


def test_pipeline_still_imports():
    from core.pipeline import Pipeline

    assert Pipeline is not None
