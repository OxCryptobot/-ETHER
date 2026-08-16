"""Honest-path progress surface (scripted + eligible)."""
from __future__ import annotations


def test_honest_path_progress_shape():
    from core.honest_path_progress import compute

    out = compute()
    assert "scripted_honest_rate" in out or out.get("scripted_n") is not None
    assert out.get("wheels_on") is True
    assert out.get("soft_launch_blocked") is True
    assert "phase1_gate" in out
    assert "eligible" in out
    assert isinstance(out.get("blockers"), list)
