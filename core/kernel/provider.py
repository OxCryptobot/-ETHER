"""Distinguish provider timeout from empty model output."""
from __future__ import annotations
from typing import Any, Dict

def classify(exc: BaseException | None = None, text: str = "") -> Dict[str, Any]:
    if exc is not None:
        name = type(exc).__name__
        if name in {"TimeoutError", "asyncio.TimeoutError"} or "timeout" in str(exc).lower():
            return {"ok": False, "error": "provider_timeout", "kind": "infra"}
        return {"ok": False, "error": name, "kind": "infra"}
    if not (text or "").strip():
        return {"ok": False, "error": "empty_model", "kind": "model"}
    return {"ok": True, "kind": "model", "n": len(text)}
