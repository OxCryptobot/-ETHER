"""Stage 4 — controlled evolution health surface for doctor / CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
QUARANTINE = ROOT / "tools" / "quarantine"
PERSISTENT = ROOT / "tools" / "persistent"
FAIL_STREAK = ROOT / "memory" / "learning" / "fail_streak.json"
FABRICATE_LOG = ROOT / "memory" / "tools" / "fabricate.jsonl"


def _count_py(dir_path: Path) -> int:
    if not dir_path.exists():
        return 0
    return sum(1 for p in dir_path.glob("*.py") if p.name not in {"_lib.py", "__init__.py"})


def _tail_jsonl(path: Path, n: int = 5) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    for line in lines[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                out.append(row)
        except json.JSONDecodeError:
            continue
    return out


def evolution_status() -> Dict[str, Any]:
    """Snapshot of controlled-evolution surface. Never raises."""
    streak = {"streak": 0, "proposed": False, "last_error": None}
    if FAIL_STREAK.exists():
        try:
            streak = json.loads(FAIL_STREAK.read_text(encoding="utf-8"))
        except Exception:
            pass

    recent = _tail_jsonl(FABRICATE_LOG, 3)
    last = recent[-1] if recent else None

    return {
        "fail_streak": int(streak.get("streak") or 0),
        "fail_proposed": bool(streak.get("proposed")),
        "fail_last_error": (streak.get("last_error") or "")[:120] or None,
        "quarantine_tools": _count_py(QUARANTINE),
        "persistent_tools": _count_py(PERSISTENT),
        "last_fabricate_status": (last or {}).get("validation_status"),
        "last_fabricate_name": (last or {}).get("name"),
        "fabricate_log_rows": len(_tail_jsonl(FABRICATE_LOG, 500)),
    }
