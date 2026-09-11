"""Agentic contract: tool path counts, generate-fallback does not."""
from __future__ import annotations

from core.loop.agentic import STAGES, classify_cycle, is_agentic_pass


def test_stages_are_the_loop() -> None:
    assert STAGES == ("observe", "tool", "sandbox", "critique", "memory")


def test_generate_fallback_is_not_agentic() -> None:
    row = {
        "policy": "model",
        "ok": True,
        "score": 1.0,
        "tools": ["generate"],
    }
    assert is_agentic_pass(row) is False


def test_tool_path_is_agentic() -> None:
    row = {
        "policy": "model",
        "ok": True,
        "score": 1.0,
        "tools": ["bug_comments", "replace_once", "run_tests"],
    }
    assert is_agentic_pass(row) is True
    assert classify_cycle(row) == "agentic_pass"


def test_craft_helper_is_not_agentic() -> None:
    assert classify_cycle({"policy": "craft_helper", "ok": True, "score": 1.0}) == "not_agentic"
