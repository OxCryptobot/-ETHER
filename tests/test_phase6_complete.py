"""Phase 6 operator OS package."""
from __future__ import annotations


def test_operator_canary():
    from core.phase6_operator import run_canary

    out = run_canary()
    assert out.get("ok") is True, out


def test_phase_board():
    from core.phase6_phase_board import board

    out = board()
    assert out.get("ok") is True
    assert out.get("n") == 5
    assert out.get("soft_launch_blocked") is True


def test_host_heal_contracts():
    from core.phase6_host_heal import check

    out = check()
    assert out.get("ok") is True, out


def test_phase6_status():
    from core.phase6_status import compute

    out = compute()
    assert out.get("phase") == "6"
    assert out.get("soft_launch_blocked") is True
    assert out.get("training_wheels") is True
    assert len(out.get("locked") or []) >= 2
