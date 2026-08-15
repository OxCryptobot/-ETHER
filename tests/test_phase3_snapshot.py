"""Phase 3 batch — measurement only; never lifts soft launch."""
from __future__ import annotations

from core.honest_live import compute_rates
from core.phase3_snapshot import build_snapshot
from scripts.foreman import STEADY_TEMPLATES


def test_steady_has_phase3_templates():
    prefixes = {t["id_prefix"] for t in STEADY_TEMPLATES}
    assert "ss_honest_live_report" in prefixes
    assert "ss_lora_dry_tick" in prefixes
    assert "ss_phase2_regression" in prefixes


def test_compute_rates_no_live_rows_blocks():
    payload = compute_rates(rows=[])
    assert payload["soft_launch_blocked"] is True
    assert payload["status"] == "no_live_rows"


def test_compute_rates_disguised_pass():
    rows = [
        {
            "ok": True,
            "mode": "live",
            "strategy": "generate",
            "degraded": [],
        }
    ]
    payload = compute_rates(rows=rows)
    assert payload["soft_launch_blocked"] is True
    assert payload["disguised_pass_n"] >= 1


def test_phase3_snapshot_ok_and_blocked():
    snap = build_snapshot()
    assert snap["soft_launch_blocked"] is True
    assert snap["training_wheels"] is True
    assert snap["lora_dry_tick"]["trained"] is False
    assert "tool_runtime_failed_terminal" in snap["tool_first_gate"]["fail_degraded"]
    assert snap["ok"] is True


def test_pipeline_still_imports():
    from core.pipeline import Pipeline

    assert Pipeline is not None
