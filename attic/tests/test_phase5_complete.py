"""Phase 5 experimental / moonshot research package."""
from __future__ import annotations


def test_moonshot_registry():
    from core.phase5_moonshots import registry

    out = registry()
    assert out.get("ok") is True, out
    assert out.get("n", 0) >= 15
    assert out.get("experimental_flags_on") is False


def test_lessons_inventory():
    from core.phase5_lessons import inventory

    out = inventory()
    assert out.get("ok") is True
    assert out.get("n_lessons", 0) >= 0


def test_research_flags_off():
    from core.phase5_research_flags import board

    out = board()
    assert out.get("ok") is True, out
    assert out.get("any_experimental_on") is False
    assert out.get("training_wheels") is True


def test_phase5_status():
    from core.phase5_status import compute

    out = compute()
    assert out.get("phase") == "5"
    assert out.get("soft_launch_blocked") is True
    assert out.get("training_wheels") is True
    assert len(out.get("locked") or []) >= 3
