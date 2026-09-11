"""Headless E2E: boot verifies gems + agentic + living. No windows."""
from scripts.ether_app import DASHBOARD, boot, health, run_e2e, shell_kind


def test_app_e2e_headless() -> None:
    report = run_e2e()
    assert report["ok"] is True
    assert report["boot"]["booted"] is True
    assert report["boot"]["verified"]["ok"] is True
    assert report["boot"]["pillars"]["gems"] is True
    assert report["stop"]["cmd"] == "stop"
    assert report["start"]["cmd"] == "attach"
    assert report["health"]["ok"] is True
    assert report["shell"] == "headless"
    assert "http" in DASHBOARD
    assert health()["dashboard"] == DASHBOARD
    assert shell_kind() == "headless"
