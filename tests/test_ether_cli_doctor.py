"""CLI doctor / phase strangler surface."""
from __future__ import annotations

from scripts.ether_cli import main


def test_doctor_runs():
    # May return 0 or 1 depending on host heartbeat in CI/host; must not crash
    rc = main(["doctor"])
    assert rc in (0, 1)


def test_phase_runs():
    assert main(["phase"]) == 0


def test_status_runs():
    assert main(["status"]) == 0


def test_moonshots_adapter_tile():
    from dashboard.collector_moonshots import collect_moonshots

    ids = {t["id"] for t in collect_moonshots()["tiles"]}
    assert "adapter" in ids
    assert "strangler" in ids
