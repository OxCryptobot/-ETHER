"""Tool-runtime gate. Generate is not a silent success path."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List

@dataclass
class ToolRuntimeGateContext:
    tool_runtime_enabled: bool
    tool_runtime_ok: bool
    tool_runtime_score: float = 0.0
    tool_runtime_error: str = ""
    degraded: List[str] = field(default_factory=list)

@dataclass
class ToolRuntimeGateOutcome:
    terminal: bool
    ok: bool
    reason: str
    degraded: List[str] = field(default_factory=list)
    score: float = 0.0

class ToolRuntimeGateHandler:
    def run(self, ctx: ToolRuntimeGateContext) -> ToolRuntimeGateOutcome:
        if not ctx.tool_runtime_enabled:
            return ToolRuntimeGateOutcome(terminal=False, ok=True, reason="tool_runtime_disabled", degraded=list(ctx.degraded), score=ctx.tool_runtime_score)
        if ctx.tool_runtime_ok:
            return ToolRuntimeGateOutcome(terminal=True, ok=True, reason="tool_runtime_ok", score=ctx.tool_runtime_score)
        degraded = list(ctx.degraded)
        if "tool_runtime_failed_terminal" not in degraded:
            degraded.append("tool_runtime_failed_terminal")
        return ToolRuntimeGateOutcome(terminal=True, ok=False, reason=ctx.tool_runtime_error or "tool_runtime_failed_terminal", degraded=degraded, score=ctx.tool_runtime_score)

def is_honest_tool_path_pass(result: Dict[str, Any]) -> bool:
    try:
        from core.kernel.honest import is_honest_tool_path_pass as _k
        return _k(result)
    except Exception:
        pass
    if not result.get("ok"):
        return False
    degraded = result.get("degraded") or []
    for d in degraded:
        s = str(d).lower()
        if "tool_runtime_fallback" in s or "tool_runtime_failed_terminal" in s:
            return False
    strategy = str(result.get("strategy") or "").lower()
    if strategy in ("repair_heavy", "generate", "best_of_n") and result.get("mode") == "live":
        return False
    return True
