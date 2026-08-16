"""Phase 5 — lessons journal inventory for day-by-day self-evolution.

Read-only scan of artifacts/lessons. Does not mutate policy.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "phase5_lessons.json"
LESSONS = ROOT / "artifacts" / "lessons"


def inventory() -> Dict[str, Any]:
    files: List[str] = []
    titles: List[str] = []
    if LESSONS.exists():
        for p in sorted(LESSONS.glob("*.json")):
            files.append(p.name)
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                title = (
                    data.get("title")
                    or data.get("id")
                    or data.get("name")
                    or data.get("lesson")
                    or p.stem
                )
                titles.append(str(title)[:120])
            except Exception:
                titles.append(p.stem)

    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "phase": "5",
        "n_lessons": len(files),
        "files": files[:50],
        "titles": titles[:50],
        "ok": True,  # empty journal is still valid
        "note": "Lessons are durable memory for evolution. Not auto-applied to LIVE.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(inventory(), indent=2))
