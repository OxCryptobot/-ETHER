"""Architecture GO vs metrics GO — soft launch stays locked."""
from __future__ import annotations


def test_architecture_go_when_scripted_strong():
    from core.phase1_gate import compute

    out = compute()
    assert "architecture_go" in out
    assert "metrics_go" in out
    assert out.get("status") in ("NO_GO", "ARCH_GO", "FULL_GO")
    # Soft launch never auto-ready
    assert out.get("soft_launch_ready") is False or out.get("training_wheels") is True
    # With current scoreboards, architecture_go should be True
    if out.get("scripted_honest_rate") and out["scripted_honest_rate"] >= 0.90:
        assert out.get("architecture_go") is True
        assert out.get("status") in ("ARCH_GO", "FULL_GO")


def test_adapter_still_default_off():
    from core.pipeline_adapter import terminal_adapter_enabled, status

    assert terminal_adapter_enabled() is False
    assert status()["default"] == "0"
