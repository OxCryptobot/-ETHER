"""live-host consumer is standalone and does not fake Ollama."""
from scripts.live_host import consume


def test_live_host_consumes_without_ollama() -> None:
    out = consume({"cmd": "attach"})
    assert out["consumed"] is True
    assert out["live_lane"] in {"ollama_4b", "grok_bus"}
    assert out["living_ok"] is True
    assert "ollama" in out
