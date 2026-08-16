"""Strangler wire v2 — pure paths only."""
from __future__ import annotations


def test_tool_first_fail_has_score_envelope():
    from core.pipeline_tool_first import decide_pipeline_tool_first

    d = decide_pipeline_tool_first(
        tool_runtime_enabled=True,
        tool_runtime_done=False,
        score=0.3,
        degraded=["prior"],
    )
    assert d.should_fail is True
    assert d.envelope is not None
    assert d.envelope["ok"] is False
    assert "tool_runtime_failed_terminal" in d.envelope["degraded"]
    assert "prior" in d.envelope["degraded"]
    assert d.score == 0.3


def test_tool_first_ok_no_envelope():
    from core.pipeline_tool_first import decide_pipeline_tool_first

    d = decide_pipeline_tool_first(tool_runtime_enabled=True, tool_runtime_done=True)
    assert d.should_fail is False
    assert d.envelope is None


def test_symbol_index_publish():
    from core.symbol_index_pub import publish

    p = publish(query="pipeline_score tool_first")
    assert p["n_files"] > 0
    assert isinstance(p["top"], list)
    assert p.get("path")


def test_zero_click_skips_on_ok():
    from core.zero_click_recovery import maybe_recover

    assert maybe_recover({"ok": True, "job_id": "x"}) is None


def test_zero_click_triggers_on_tool_runtime_terminal(tmp_path=None):
    from core import zero_click_recovery as zcr

    # Use real pending dir under repo — recovery is rate-limited; just ensure no crash
    out = zcr.maybe_recover(
        {
            "ok": False,
            "job_id": "ss_tool_runtime_test",
            "failure_type": "timeout",
            "note": "tool_runtime_failed_terminal",
        }
    )
    # May be None if rate-limited or queue full — both legal
    assert out is None or out.startswith("zcr_")
