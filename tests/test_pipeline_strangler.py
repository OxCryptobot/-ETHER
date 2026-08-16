"""Pipeline strangler — pure slices only. Does not execute Pipeline.run."""
from __future__ import annotations


def test_pipeline_strangler_status():
    from core.pipeline_strangler import compute

    s = compute()
    assert s["pipeline_bytes"] > 0
    assert s["extracted_n"] >= 4
    assert s["extracted_ok"] == s["extracted_n"]
    assert s["tool_first_contract_ok"] is True
    assert s["status"] in ("STRANGLER_ACTIVE", "HEALTHY_SLICE", "IN_PROGRESS")
    assert s.get("path")


def test_tool_first_fail_when_not_done():
    from core.pipeline_tool_first import decide_pipeline_tool_first

    d = decide_pipeline_tool_first(tool_runtime_enabled=True, tool_runtime_done=False)
    assert d.should_fail is True
    assert d.degrade_marker == "tool_runtime_failed_terminal"


def test_tool_first_pass_when_done():
    from core.pipeline_tool_first import decide_pipeline_tool_first

    d = decide_pipeline_tool_first(tool_runtime_enabled=True, tool_runtime_done=True)
    assert d.should_fail is False


def test_pipeline_select_returns_strategy():
    from core.pipeline_select import select_strategy

    name = select_strategy("test objective for select")
    assert isinstance(name, str)
    assert len(name) > 0


def test_microbench_import_contract():
    """Microbench must be callable; may freeze only if red — do not assert freeze."""
    from core.microbench import run, is_steady_frozen

    out = run()
    assert "ok" in out
    assert "steps" in out
    assert isinstance(is_steady_frozen(), bool)
