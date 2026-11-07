"""ReAct. Three turns. One tool per turn. A repeat stops."""
from __future__ import annotations

from typing import Any, Callable, Dict, List

from core.agent.skills import call


def _key(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    return text[start : end + 1] if start >= 0 and end > start else text[:80]


def react(ask: Callable[..., str], root, prompt: str, turns: int = 3) -> Dict[str, Any]:
    """Reason, act, observe. Cap at three turns. Same tool twice stops."""
    scratch = ""
    seen: List[str] = []
    used = False
    last = ""
    for _ in range(max(1, turns)):
        try:
            text = ask(prompt + scratch, n=240)
        except Exception as exc:
            return {"ok": False, "text": last, "used": used, "error": str(exc)[:120]}
        last = text
        key = _key(text)
        if key in seen:
            return {"ok": False, "text": last, "used": used, "note": "repeat"}
        seen.append(key)
        tool = call(root, text)
        if tool is None:
            return {"ok": True, "text": last, "used": used}
        used = True
        hit = (tool.get("hits") or [""])[0]
        scratch += f"\nObservation: {tool.get('skill')} ok={tool.get('ok')} {hit}\n"
    return {"ok": True, "text": last, "used": used}
