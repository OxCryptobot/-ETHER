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


def test_agent_turn_and_edit() -> None:
    from scripts.ether_app import agent_turn, grep_repo, write_file, edit_file
    assert grep_repo("live_host")["ok"] is True
    write_file("artifacts/batch_probe.txt", "one")
    assert edit_file("artifacts/batch_probe.txt", "one", "two")["ok"] is True
    out = agent_turn("live_host")
    assert "reply" in out
    assert out["verified"] in {True, False}


def test_mark_alive() -> None:
    from scripts.ether_app import ROOT, mark_alive
    row = mark_alive()
    assert row["alive"] is True
    assert (ROOT / "artifacts" / "app_alive.json").is_file()


def test_ensure_keepalive_offbox() -> None:
    from scripts.ether_app import ensure_keepalive
    row = ensure_keepalive()
    assert row["ok"] is True
    assert "armed" in row
