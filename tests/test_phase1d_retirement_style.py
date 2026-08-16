"""Phase 1D retirement + style gate expansion."""
from __future__ import annotations


def test_strangler_style_includes_new_modules():
    from core.strangler_style_gate import TARGETS, check

    assert "core/pipeline_oracle.py" in TARGETS
    assert "core/timeout_retirement.py" in TARGETS
    assert "core/live_fixture_policy.py" in TARGETS
    out = check()
    assert out.get("ok") is True
    assert out.get("ok_n") == out.get("n")


def test_phase1d_has_retirement_check():
    from core.phase1d_status import compute

    out = compute()
    ids = {c["id"] for c in out.get("checks") or []}
    assert "timeout_retirement_plan" in ids
    assert "soft_launch_still_blocked" in ids
    assert out.get("training_wheels") is True
    assert out.get("soft_launch") is False


def test_moonshots_has_retire_tile():
    from dashboard.collector_moonshots import collect_moonshots

    m = collect_moonshots()
    ids = {t["id"] for t in m.get("tiles") or []}
    assert "timeout_retire" in ids
