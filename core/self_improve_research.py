"""Internal research — lessons, fail_learn, critiques. No new HTTP stack.

External papers stay tutor-side (Grok). Local agent searches the corpus it owns.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
LESSONS = ROOT / "memory" / "ether_apprentice" / "lessons"
CRITIQUES = ROOT / "artifacts" / "critiques"


def _scan_json(folder: Path, needle: str, *, limit: int = 8) -> List[Dict[str, Any]]:
    hits: List[Dict[str, Any]] = []
    if not folder.exists():
        return hits
    q = (needle or "").lower()
    for path in sorted(folder.glob("*.json")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if q and q not in text.lower() and q not in path.name.lower():
            continue
        try:
            data = json.loads(text)
        except Exception:
            data = {"raw": text[:200]}
        if not isinstance(data, dict):
            data = {"raw": str(data)[:200]}
        hits.append(
            {
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "id": data.get("id") or path.stem,
                "rule": str(data.get("rule") or data.get("lesson") or data.get("note") or "")[:240],
            }
        )
        if len(hits) >= limit:
            break
    return hits


def research(gap: str) -> Dict[str, Any]:
    lessons = _scan_json(LESSONS, gap, limit=6)
    critiques = _scan_json(CRITIQUES, gap, limit=4)
    fail_lessons: List[Dict[str, Any]] = []
    try:
        from core.fail_learn import LEARN, classify_name

        kind = classify_name(gap, gap)
        meta = LEARN.get(kind) or LEARN["other"]
        fail_lessons.append({"kind": kind, **meta})
    except Exception:
        pass
    return {
        "gap": gap,
        "lessons": lessons,
        "critiques": critiques,
        "fail_learn": fail_lessons,
        "external": "escalate_grok — tutor searches docs/papers; local corpus is lessons+critiques",
        "n": len(lessons) + len(critiques),
    }
