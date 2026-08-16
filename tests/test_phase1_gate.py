"""Phase 1 gate to Phase 2 — metrics GO/NO_GO + architecture_go."""
from __future__ import annotations


def test_phase1_gate_structure():
    from core.phase1_gate import compute

    out = compute()
    assert out.get("phase_gate") == "1_to_2"
    assert out.get("status") in ("GO", "NO_GO", "ARCH_GO", "FULL_GO")
    assert "metrics_go" in out
    assert "architecture_go" in out
    ids = {c["id"] for c in out.get("checks") or []}
    assert "timeout_rate_eligible" in ids
    assert "honest_rate_eligible" in ids
    assert out.get("soft_launch_ready") is False or out.get("training_wheels") is True


def test_soft_launch_still_blocked():
    from core.soft_launch import evaluate

    out = evaluate()
    assert out.get("soft_launch_blocked") is True
    assert "training_wheels_on" in (out.get("blocked_reasons") or []) or out.get(
        "training_wheels"
    )
