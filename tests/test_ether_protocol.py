"""ether:// parse is attach/stop. No fake Ollama."""
from scripts.ether_protocol import handle, parse_target


def test_parse_targets() -> None:
    assert parse_target("ether://attach") == "attach"
    assert parse_target("ether://stop") == "stop"


def test_handle_attach_fail_closed() -> None:
    out = handle("ether://attach")
    assert out["consumed"] is True
    assert out["live_lane"] in {"ollama_4b", "grok_bus"}
