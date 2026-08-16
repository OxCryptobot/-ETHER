"""Phase 2 architecture package tests."""
from __future__ import annotations


def test_slices_canary():
    from core.pipeline_slices_canary import run_matrix

    out = run_matrix()
    assert out.get("ok") is True, out
    assert out.get("adapter_enabled") is False


def test_phase2_status_surface():
    from core.phase2_status import compute

    out = compute()
    assert out.get("phase") == "2"
    assert out.get("soft_launch_blocked") is True
    assert out.get("training_wheels") is True
    assert isinstance(out.get("locked_until_metrics_go"), list)
    assert len(out.get("packages") or []) >= 5
    # Architecture path should be complete under current canaries
    if out.get("architecture_go"):
        assert out.get("architecture_complete") is True or out.get("status") in (
            "ARCH_COMPLETE",
            "ARCH_IN_PROGRESS",
        )


def test_adapter_and_wheels_doctrine():
    from core.pipeline_adapter import terminal_adapter_enabled

    assert terminal_adapter_enabled() is False
