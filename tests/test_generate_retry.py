"""leftover 5%: generate/retry prompts extracted; grok_bus needs no API key."""
from __future__ import annotations

import inspect

from core.loop.generate_retry import first_prompt, retry_prompt
from core.model_router import grok_present, select_backend
from core.pipeline import Pipeline


def test_pipeline_uses_generate_retry() -> None:
    src = inspect.getsource(Pipeline.run)
    assert "first_prompt" in src
    assert "build_retry" in src or "retry_prompt" in src


def test_first_and_retry_named() -> None:
    p = first_prompt("add", "direct", "{}", multifile=True)
    assert "Return only executable Python" in p
    assert "add" in p
    r = retry_prompt("add", "x=1", "boom", "direct", burst=True)
    assert "[Elevated model / burst retry]" in r


def test_grok_present_default() -> None:
    assert grok_present() is True
    b = select_backend({"class": "live"}, vram=4096)
    assert b["backend"] in {"grok_bus", "outsource", "ollama"}
