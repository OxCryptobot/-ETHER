"""Phase 3.5 hygiene — kill job removed; measure path required."""
from __future__ import annotations

from scripts.foreman import STEADY_TEMPLATES
from core.measure_tick import run as measure_run
from core.soft_launch import evaluate


def test_steady_has_no_kill_live_pending():
    prefixes = {t["id_prefix"] for t in STEADY_TEMPLATES}
    assert "ss_kill_live_pending" not in prefixes
    assert "ss_measure_tick" in prefixes


def test_measure_tick_and_soft_launch_blocked():
    out = measure_run()
    assert out["soft_launch_blocked"] is True
    gate = evaluate()
    assert gate["soft_launch_ready"] is False


def test_pipeline_still_imports():
    from core.pipeline import Pipeline

    assert Pipeline is not None
