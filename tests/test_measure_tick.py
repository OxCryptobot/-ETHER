"""Phase 3.4 — measure tick is always safe and never lifts soft launch."""
from __future__ import annotations

from pathlib import Path

from core.measure_tick import run


def test_measure_tick_writes_artifacts():
    out = run()
    assert "steps" in out
    assert "honest_live" in out["steps"]
    assert "soft_launch" in out["steps"]
    assert out["soft_launch_blocked"] is True
    root = Path(__file__).resolve().parents[1]
    # Files should exist after a successful honest_live step
    if out["steps"]["honest_live"].get("ok"):
        assert (root / "artifacts" / "honest_live_rates.json").is_file()
    if out["steps"]["soft_launch"].get("ok"):
        assert out["steps"]["soft_launch"].get("soft_launch_ready") is False


def test_pipeline_still_imports():
    from core.pipeline import Pipeline

    assert Pipeline is not None
