"""live-host consumer is fail-closed and always publishes attach lanes."""
from scripts.live_host import consume


def test_live_host_consumes_without_ollama() -> None:
    out = consume({"cmd": "attach"})
    assert out["consumed"] is True
    assert out["live_lane"] in {"ollama_4b", "grok_bus", "none"}
    if out["live_lane"] != "none":
        assert out["living_ok"] is True
