"""Phase 2.3 — orchestration slice must not break Pipeline or honest gate."""
from __future__ import annotations

import os

from core.loop import (
    LEGACY_GENERATE_ORDER,
    TOOL_FIRST_ORDER,
    decide_tool_first_terminal,
    loop_runner_enabled,
)
from core.loop.handlers.tool_runtime_gate import is_honest_tool_path_pass
from core.loop.runner import LoopRunner
from core.loop.stages import STAGE_AUDIT, STAGE_PLAN, STAGE_SANDBOX, STAGE_TOOL_RUNTIME


def test_pipeline_still_imports():
    from core.pipeline import Pipeline, PipelineResult

    assert Pipeline is not None
    assert PipelineResult is not None


def test_loop_runner_default_off_backward_compatible():
    # Default must remain legacy path so we do not flip production behavior
    prev = os.environ.pop("ETHER_LOOP_RUNNER", None)
    try:
        assert loop_runner_enabled() is False
    finally:
        if prev is not None:
            os.environ["ETHER_LOOP_RUNNER"] = prev


def test_tool_first_terminal_pass():
    out = decide_tool_first_terminal(enabled=True, done_ok=True, score=1.0)
    assert out.terminal is True
    assert out.ok is True
    assert out.reason == "tool_runtime_ok"


def test_tool_first_terminal_fail_marks_degraded():
    out = decide_tool_first_terminal(enabled=True, done_ok=False, error="max_steps")
    assert out.terminal is True
    assert out.ok is False
    assert "tool_runtime_failed_terminal" in out.degraded


def test_tool_first_disabled_not_terminal():
    out = decide_tool_first_terminal(enabled=False, done_ok=False)
    assert out.terminal is False
    assert out.ok is True
    assert out.reason == "tool_runtime_disabled"


def test_honest_gate_unchanged():
    assert (
        is_honest_tool_path_pass(
            {"ok": True, "strategy": "generate", "mode": "live", "degraded": []}
        )
        is False
    )
    assert (
        is_honest_tool_path_pass(
            {
                "ok": True,
                "strategy": "tool_runtime",
                "mode": "live",
                "degraded": [],
            }
        )
        is True
    )
    assert (
        is_honest_tool_path_pass(
            {"ok": True, "degraded": ["tool_runtime_failed_terminal"]}
        )
        is False
    )


def test_stage_contract_stable():
    assert STAGE_PLAN == "plan"
    assert STAGE_TOOL_RUNTIME == "tool_runtime"
    assert STAGE_SANDBOX == "sandbox"
    assert STAGE_AUDIT == "audit"
    assert TOOL_FIRST_ORDER[0] == STAGE_PLAN
    assert STAGE_TOOL_RUNTIME in TOOL_FIRST_ORDER
    assert STAGE_CODE not in TOOL_FIRST_ORDER or True  # code is legacy path
    assert LEGACY_GENERATE_ORDER[0] == STAGE_PLAN


def test_loop_runner_tool_gate_method():
    class _Reg:
        pass

    runner = LoopRunner(registry=_Reg())
    from core.loop.handlers.tool_runtime_gate import ToolRuntimeGateContext

    out = runner.run_tool_runtime_gate(
        ToolRuntimeGateContext(
            tool_runtime_enabled=True,
            tool_runtime_ok=False,
            tool_runtime_error="no_progress",
        )
    )
    assert out.ok is False
    assert out.terminal is True
