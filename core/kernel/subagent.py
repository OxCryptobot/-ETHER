"""One isolated call. The child sees a copy of the context, not the parent scratch."""
from __future__ import annotations

from typing import Any, Callable, Dict


def isolate(goal: str, context: str, fn: Callable[[Dict[str, str]], Any]) -> Dict[str, Any]:
    box = {"goal": goal, "context": context}
    try:
        result = fn(dict(box))
        error = None
    except Exception as exc:
        result = None
        error = type(exc).__name__
    return {
        "goal": goal,
        "context_chars": len(context),
        "ok": error is None,
        "error": error,
        "result": result,
    }
