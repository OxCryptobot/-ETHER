"""Phase 7 north-star system package."""
from __future__ import annotations


def test_pillars():
    from core.phase7_pillars import check

    out = check()
    assert out.get("ok") is True, out
    assert out.get("pillars_n") == 3


def test_living_checklist():
    from core.phase7_living_checklist import checklist

    out = checklist()
    assert out.get("ok") is True, out
    assert out.get("autonomous_claim") is False
    assert out.get("gap_n", 1) == 0


def test_roadmap():
    from core.phase7_roadmap import rollup

    out = rollup()
    assert out.get("ok") is True
    assert out.get("soft_launch_blocked") is True
    assert len(out.get("remaining_real_work") or []) >= 3


def test_phase7_status():
    from core.phase7_status import compute

    out = compute()
    assert out.get("phase") == "7"
    assert out.get("soft_launch_blocked") is True
    assert out.get("autonomous_claim") is False
    assert out.get("training_wheels") is True
