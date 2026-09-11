"""LIVE attach publishes a lane. Does not fake a GPU."""
from __future__ import annotations

from core.loop.live_attach import publish


def test_publish_has_lanes() -> None:
    out = publish()
    assert out["fast_lane"] == "matrix-worker"
    assert out["live_lane"] in {"ollama_4b", "grok_bus", "none"}
    assert out["ok"] is True
