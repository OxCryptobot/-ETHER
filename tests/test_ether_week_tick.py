"""FAST contract: week tick writes energy + board."""
from scripts.ether_week_tick import tick


def test_week_tick_writes_energy() -> None:
    row = tick(push=False)
    assert row["ok"] is True
    assert "last_gem" in row
