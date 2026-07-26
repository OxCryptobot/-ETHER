"""Attach last auto health report into snapshot (cheap read)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
LATEST = ROOT / "memory" / "health" / "latest.json"


def load_auto_health() -> Dict[str, Any]:
    if not LATEST.exists():
        return {"status": "unknown", "message": "run python scripts/health_check.py"}
    try:
        data = json.loads(LATEST.read_text(encoding="utf-8"))
        return {
            "status": data.get("status"),
            "ok": data.get("ok"),
            "timestamp": data.get("timestamp"),
            "counts": data.get("counts"),
            "failed": [c["id"] for c in (data.get("checks") or []) if not c.get("ok")],
            "tips": data.get("tips") or [],
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
