"""p2 leftover: burst/multifile/strip helpers live off Pipeline."""
from __future__ import annotations

from core.loop.pipeline_util import is_burst_model, looks_multifile, strip_fences
from core.pipeline import Pipeline


def test_is_burst_model_exact() -> None:
    assert is_burst_model("grok-3") is True
    assert is_burst_model("burst") is True
    assert is_burst_model("llama3") is False
    assert is_burst_model("") is False


def test_looks_multifile_word_boundary() -> None:
    assert looks_multifile("refactor this module") is True
    assert looks_multifile("add.py helper") is True
    assert looks_multifile("add two numbers") is False


def test_strip_fences() -> None:
    assert strip_fences("```python\nx=1\n```") == "x=1"
    assert Pipeline()._strip("```\ny=2\n```") == "y=2"
