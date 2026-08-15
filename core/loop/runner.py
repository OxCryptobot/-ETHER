"""Thin stage dispatcher. Knows stage names; nothing about locking or LLMs.

Phase 2.3: ToolRuntimeGateHandler is part of the runner surface so Pipeline
can call one place for terminal tool-first decisions.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from core.loop.handlers.finalize import FinalizeContext, FinalizeHandler, FinalizeOutcome
from core.loop.handlers.tool_runtime_gate import (
    ToolRuntimeGateContext,
    ToolRuntimeGateHandler,
    ToolRuntimeGateOutcome,
)
from core.loop.handlers.verify import (
    VerificationContext,
    VerificationHandler,
    VerificationOutcome,
)


def _default_run_tool(name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    from gems.grandidierite.registry import run_tool

    return run_tool(name, payload)


class LoopRunner:
    def __init__(self, registry: Any, run_tool: Optional[Callable[..., Dict[str, Any]]] = None):
        tool = run_tool or _default_run_tool
        self._finalize = FinalizeHandler(registry=registry, run_tool=tool)
        self._verify = VerificationHandler(registry=registry, run_tool=tool)
        self._tool_gate = ToolRuntimeGateHandler()

    def run_finalize(self, ctx: FinalizeContext) -> FinalizeOutcome:
        return self._finalize.run(ctx)

    def run_verify(self, ctx: VerificationContext) -> VerificationOutcome:
        return self._verify.run(ctx)

    def run_tool_runtime_gate(self, ctx: ToolRuntimeGateContext) -> ToolRuntimeGateOutcome:
        return self._tool_gate.run(ctx)
