"""Thin stage dispatcher. Knows stage names; nothing about locking or LLMs."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from core.loop.handlers.finalize import FinalizeContext, FinalizeHandler, FinalizeOutcome
from core.loop.handlers.verify import (
    VerificationContext,
    VerificationHandler,
    VerificationOutcome,
)


def _default_run_tool(name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Lazy gem bridge — the only gems import in core/loop (allowed by D2)."""
    from gems.grandidierite.registry import run_tool

    return run_tool(name, payload)


class LoopRunner:
    def __init__(self, registry: Any, run_tool: Optional[Callable[..., Dict[str, Any]]] = None):
        self._finalize = FinalizeHandler(registry=registry, run_tool=run_tool or _default_run_tool)
        self._verify = VerificationHandler(
            registry=registry, run_tool=run_tool or _default_run_tool
        )

    def run_finalize(self, ctx: FinalizeContext) -> FinalizeOutcome:
        return self._finalize.run(ctx)

    def run_verify(self, ctx: VerificationContext) -> VerificationOutcome:
        return self._verify.run(ctx)
