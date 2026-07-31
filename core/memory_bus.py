"""Shared memory bus for the gem infinity loop.

Topology (essential, not optional):

    Selenite → Rose Quartz → Clear Quartz → Black Tourmaline
         ↑                                           |
         |                                     Labradorite (critique)
         |                                           |
         └──────── Amethyst ←── Citrine ←────────────┘

Critiques and verified outcomes are written here so the *next* plan can
self-tune. Local JSONL is always written; Citrine is best-effort when Qdrant
is up. Retrieval is leak-aware: callers must still run prompt_guard on any
holdout path.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.spine.state_io import append_jsonl

ROOT = Path(__file__).resolve().parents[1]
BUS_DIR = ROOT / "memory" / "bus"
CRITIQUES_PATH = BUS_DIR / "critiques.jsonl"
LESSONS_PATH = BUS_DIR / "lessons.jsonl"


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-zA-Z_][\w]{2,}", (text or "").lower()) if len(t) > 2}


def record_critique(
    *,
    objective: str,
    code: str,
    critique: str,
    suggestions: Optional[List[str]] = None,
    complexity_score: float = 0.0,
    success: bool = False,
    confidence: float = 0.0,
    strategy: str = "",
    task_id: str = "",
) -> Dict[str, Any]:
    """Persist a Labradorite review for the self-improvement loop."""
    BUS_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kind": "critique",
        "task_id": task_id,
        "objective": (objective or "")[:500],
        "critique": (critique or "")[:1000],
        "suggestions": list(suggestions or [])[:12],
        "complexity_score": float(complexity_score or 0.0),
        "success": bool(success),
        "confidence": float(confidence or 0.0),
        "strategy": strategy or "",
        "code_chars": len(code or ""),
    }
    try:
        append_jsonl(CRITIQUES_PATH, entry)
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}

    # Structured lesson for planner (success or failure both teach)
    lesson = {
        "timestamp": entry["timestamp"],
        "kind": "lesson",
        "objective": entry["objective"],
        "success": entry["success"],
        "text": _lesson_text(entry),
        "suggestions": entry["suggestions"],
    }
    try:
        append_jsonl(LESSONS_PATH, lesson)
    except Exception:
        pass

    # Best-effort Citrine (failures collection for misses, patterns meta for hits)
    try:
        from core.patterns import is_optional_vector_offline
        from core.registry import build_default_registry
        from core.schemas import CitrineRequest, Envelope
        from uuid import uuid4

        collection = "patterns" if success else "failures"
        docs = [
            {
                "text": f"OBJECTIVE:\n{entry['objective']}\n\nCRITIQUE:\n{entry['critique']}\n\n"
                + ("\n".join(entry["suggestions"]) if entry["suggestions"] else ""),
                "metadata": {
                    "kind": "critique",
                    "success": success,
                    "strategy": strategy,
                    "task_id": task_id,
                },
            }
        ]
        res = build_default_registry().execute(
            Envelope(
                task_id=uuid4(),
                target_gem="citrine",
                payload=CitrineRequest(action="add", collection=collection, documents=docs),
            )
        )
        if res.error and not is_optional_vector_offline(res.error.message):
            entry["citrine_error"] = res.error.message[:160]
        else:
            entry["citrine"] = collection
    except Exception as e:
        entry["citrine_error"] = str(e)[:160]

    return {"ok": True, "entry": entry}


def _lesson_text(entry: Dict[str, Any]) -> str:
    tag = "PASS" if entry.get("success") else "FAIL"
    bits = [f"[{tag}] {entry.get('critique') or ''}"]
    for s in entry.get("suggestions") or []:
        bits.append(f"- {s}")
    return "\n".join(bits)[:800]


def recent_lessons(objective: str, k: int = 5) -> str:
    """Rank recent bus lessons by token overlap with the objective (for Selenite)."""
    path = LESSONS_PATH if LESSONS_PATH.exists() else CRITIQUES_PATH
    if not path.exists():
        return ""
    q = _tokens(objective)
    rows: List[Dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-200:]
        for line in lines:
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        return ""

    scored: List[tuple[float, Dict[str, Any]]] = []
    for r in rows:
        ot = _tokens(str(r.get("objective") or ""))
        overlap = len(q & ot) / max(1, len(q))
        # prefer failures slightly for repair signal
        boost = 0.05 if not r.get("success", True) else 0.0
        scored.append((overlap + boost, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    picked = [r for s, r in scored if s > 0][:k] or rows[-k:]
    blocks = []
    for r in picked:
        text = r.get("text") or r.get("critique") or ""
        if text.strip():
            blocks.append(text.strip()[:400])
    if not blocks:
        return ""
    return "Prior critique lessons (self-improvement loop):\n" + "\n---\n".join(blocks)
