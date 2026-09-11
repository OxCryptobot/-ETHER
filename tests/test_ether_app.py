"""Headless E2E for the in-house app. No window. No fake Ollama."""
from scripts.ether_app import DASHBOARD, boot, health, run_e2e, shell_kind


def test_app_e2e_headless() -> None:
    report = run_e2e()
    assert report["ok"] is True
    assert report["boot"]["booted"] is True
    assert report["stop"]["cmd"] == "stop"
    assert report["start"]["cmd"] == "attach"
    assert report["health"]["ok"] is True
    assert report["shell"] in {"webview", "browser_fallback"}
    assert "http" in DASHBOARD
    assert health()["dashboard"] == DASHBOARD
    boot_again = boot()
    assert boot_again["live_lane"] in {"ollama_4b", "grok_bus"}
    assert shell_kind() in {"webview", "browser_fallback"}
