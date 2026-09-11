"""App boot/start/stop. Dashboard URL is UX only."""
from scripts.ether_app import DASHBOARD, boot, live_start, live_stop, status_line


def test_boot_and_dashboard_contract() -> None:
    state = boot()
    assert state["booted"] is True
    assert "etherbot.grok.me" in DASHBOARD or DASHBOARD.startswith("http")
    assert state["live_lane"] in {"ollama_4b", "grok_bus"}
    assert live_start()["cmd"] == "attach"
    assert live_stop()["cmd"] == "stop"
    assert "ollama" in status_line(state)
