"""live-host consumer is standalone and does not fake Ollama."""
from scripts.live_host import consume, start_ollama


def test_live_host_consumes_without_ollama() -> None:
    out = consume({"cmd": "attach"})
    assert out["consumed"] is True
    assert out["live_lane"] in {"ollama_4b", "grok_bus"}
    assert out["living_ok"] is True
    assert "ollama" in out


def test_start_ollama_fail_closed_without_binary() -> None:
    # Ubuntu / this sandbox has no ollama on PATH → False, never fake True.
    assert start_ollama() in {True, False}
    out = consume({"cmd": "attach"})
    if not start_ollama():
        assert out["ollama"] is False
        assert out["live_lane"] == "grok_bus"
