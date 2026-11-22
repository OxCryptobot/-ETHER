"""ReAct. Three turns. One tool per turn. A repeat stops."""
from __future__ import annotations

from typing import Any, Callable, Dict, List

from core.agent.skills import MODEL_SKILLS, call, model_skills

_DEFAULT = object()


def _key(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    return text[start : end + 1] if start >= 0 and end > start else text[:80]


def react(ask: Callable[..., str], root, prompt: str, turns: int = 3, n: int = 240,
          allowed: Any = _DEFAULT) -> Dict[str, Any]:
    """Reason, act, observe. Cap at three turns. Same tool twice stops. n = reply token cap.

    Batch 9: only read-only skills (`allowed`, default MODEL_SKILLS = search, read) run from a
    reply; a denied call is an observation, never a write. Batch 10: the default is model_skills(),
    which adds read-only skills (batch 10: `mcp`, `lsp`) only when their flags are on."""
    if allowed is _DEFAULT:
        allowed = model_skills()
    scratch = ""
    seen: List[str] = []
    used = False
    last = ""
    for _ in range(max(1, turns)):
        try:
            text = ask(prompt + scratch, n=n)
        except Exception as exc:
            return {"ok": False, "text": last, "used": used, "error": str(exc)[:120]}
        last = text
        key = _key(text)
        if key in seen:
            return {"ok": False, "text": last, "used": used, "note": "repeat"}
        seen.append(key)
        try:
            from core.agent.gems import security

            if security(root, text).get("next") == "stop":
                return {"ok": False, "text": text, "used": used, "note": "blocked"}
        except Exception:
            pass
        tool = call(root, text, allowed=allowed)
        if tool is None:
            return {"ok": True, "text": last, "used": used}
        used = True
        hit = (tool.get("hits") or [""])[0]
        scratch += f"\nObservation: {tool.get('skill')} ok={tool.get('ok')} {hit}\n"
        try:
            from core.agent.gems import chain

            row = chain(root, text, tool.get("skill") or "")
            if not row.get("ok"):
                return {"ok": False, "text": text, "used": used, "note": row.get("note")}
        except Exception:
            pass
    return {"ok": True, "text": last, "used": used}
