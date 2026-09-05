"""p2 leftover: available_tools is the named entry for Selenite's tool list."""
from __future__ import annotations

import inspect

from core.loop.tools_avail import available_tools
from core.pipeline import Pipeline


def test_pipeline_uses_available_tools() -> None:
    src = inspect.getsource(Pipeline.run)
    assert "available_tools" in src
    assert "grandidierite_list_tools_unavailable" not in src


def test_available_tools_degrades_on_failure(monkeypatch) -> None:
    class R:
        degraded: list = []

    def boom():
        raise RuntimeError("no registry")

    monkeypatch.setattr("gems.grandidierite.registry.list_tools", boom)
    r = R()
    out = available_tools(r)
    assert out == []
    assert any("grandidierite_list_tools_unavailable" in x for x in r.degraded)
