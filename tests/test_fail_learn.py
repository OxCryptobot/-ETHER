"""Failed-job classifier — learning pack, not a replay hammer."""
from __future__ import annotations

from core.fail_learn import analyze, classify_name


def test_classify_known_kinds():
    assert classify_name("p1_243_hard_live_tools_unit_wheels_skip.json") == "wheels_skip"
    assert classify_name("p1_245_hard_tools_unit.json") == "unit_hard_tools"
    assert classify_name("p1_112_gate_sample_merge_002702.json") == "hard_live_observe_loop"
    assert classify_name("p1_110_gate_sample_greeter_002700.json") == "easy_gate_sample_stale"


def test_analyze_writes_lessons():
    out = analyze()
    assert out.get("training_wheels") is True
    assert out.get("soft_launch") is False
    assert "counts" in out
    assert out.get("path")
