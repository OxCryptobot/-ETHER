"""Keepalive tick uses live-host consume. Operator path is Matrix Start LIVE."""
from scripts.ether_keepalive import tick


def test_keepalive_tick() -> None:
    out = tick()
    assert out.get("consumed") is True
    assert out.get("live_lane") in {"ollama_4b", "grok_bus"}
