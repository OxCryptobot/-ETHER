"""Compile last events into a short next-job briefing for the 4B."""
from __future__ import annotations
from typing import Any, Dict, Iterable, List

def compile_briefing(events: Iterable[Dict[str, Any]], *, max_chars: int = 800) -> str:
    lines: List[str] = []
    for ev in list(events)[-12:]:
        kind = str(ev.get("kind") or "event")
        extra = ev.get("job_id") or ev.get("tool") or ev.get("reason") or ""
        lines.append(f"{kind} {extra}".strip())
    return "\n".join(lines)[:max_chars]
