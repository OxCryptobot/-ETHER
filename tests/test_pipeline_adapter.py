"""Flag-gated adapter — default preserves legacy."""
from __future__ import annotations

import os


def test_adapter_off_by_default():
    from core.pipeline_adapter import terminal_adapter_enabled, maybe_decide_terminal, status

    old = os.environ.get("ETHER_PIPELINE_TERMINAL")
    try:
        os.environ.pop("ETHER_PIPELINE_TERMINAL", None)
        assert terminal_adapter_enabled() is False
        assert (
            maybe_decide_terminal(
                tool_runtime_enabled=True, tool_runtime_done=False
            )
            is None
        )
        st = status()
        assert st["enabled"] is False
        assert st["default"] == "0"
    finally:
        if old is None:
            os.environ.pop("ETHER_PIPELINE_TERMINAL", None)
        else:
            os.environ["ETHER_PIPELINE_TERMINAL"] = old


def test_adapter_on_returns_terminal():
    from core.pipeline_adapter import maybe_decide_terminal, terminal_adapter_enabled

    old = os.environ.get("ETHER_PIPELINE_TERMINAL")
    try:
        os.environ["ETHER_PIPELINE_TERMINAL"] = "1"
        assert terminal_adapter_enabled() is True
        out = maybe_decide_terminal(
            tool_runtime_enabled=True,
            tool_runtime_done=False,
            score=0.1,
        )
        assert out is not None
        assert out["should_fail"] is True
        assert out["marker"] == "tool_runtime_failed_terminal"

        ok = maybe_decide_terminal(
            tool_runtime_enabled=True, tool_runtime_done=True, score=1.0
        )
        assert ok is not None
        assert ok["ok"] is True
    finally:
        if old is None:
            os.environ.pop("ETHER_PIPELINE_TERMINAL", None)
        else:
            os.environ["ETHER_PIPELINE_TERMINAL"] = old
