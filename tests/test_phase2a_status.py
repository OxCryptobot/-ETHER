"""Phase 2A status surface."""
from __future__ import annotations


def test_phase2a_status():
    from core.phase2a_status import compute

    out = compute()
    assert out.get("phase") == "2A"
    assert out.get("soft_launch_blocked") is True
    ids = {c["id"] for c in out.get("checks") or []}
    assert "terminal_canary" in ids
    assert "score_canary" in ids
    assert "adapter_off" in ids
    assert "architecture_go" in ids
    assert "wheels_on" in ids
    # Adapter must stay OFF during 2A canary phase
    adapter = next(c for c in out["checks"] if c["id"] == "adapter_off")
    assert adapter["ok"] is True, adapter
