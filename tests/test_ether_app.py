"""Desktop app actions do not need a display. Fail-closed Ollama."""
from scripts.ether_app import live_start, live_stop, status_line


def test_live_start_stop() -> None:
    on = live_start()
    assert on["cmd"] == "attach"
    assert on["live_lane"] in {"ollama_4b", "grok_bus"}
    off = live_stop()
    assert off["cmd"] == "stop"
    assert "ollama" in status_line(on)
