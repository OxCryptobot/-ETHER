"""One lesson per UTC day. Infra failures are not lessons. Yesterday's thinking is kept."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def _load(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _newest_fail(root: Path) -> Optional[Dict[str, Any]]:
    failed = root / "artifacts" / "jobs" / "failed"
    if not failed.is_dir():
        return None
    files = sorted(failed.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files:
        if path.stem.startswith("medic"):
            continue
        row = _load(path)
        report = row.get("report") if isinstance(row.get("report"), dict) else {}
        if report:
            report.setdefault("job_id", row.get("id") or path.stem)
            return report
        if row.get("ok") is False or row.get("error") or row.get("tail"):
            row.setdefault("job_id", row.get("id") or path.stem)
            return row
    return None


def learn(root: Path, now: Optional[datetime] = None) -> Dict[str, Any]:
    root = Path(root)
    today = (now or datetime.now(timezone.utc)).date().isoformat()
    path = root / "artifacts" / "day_learn.json"
    prev = _load(path)
    preserved = prev.get("lesson")
    if prev.get("day") == today:
        return {"ok": True, "skipped": True, "day": today, "preserved": preserved}
    from core.kernel.self_learn import lesson_from_fail

    lesson = lesson_from_fail(_newest_fail(root))
    row: Dict[str, Any] = {
        "ok": True,
        "day": today,
        "skipped": False,
        "lesson": lesson,
        "preserved": preserved,
        "thinking": None,
    }
    if lesson:
        row["thinking"] = {
            "before_action": lesson.get("smallest_experiment"),
            "evidence": lesson.get("evidence"),
            "root_cause": lesson.get("root_cause"),
            "kept": False,
        }
        try:
            from core.kernel.edit_memory import remember
            remember(root, f"day {today}: {lesson.get('root_cause')}: {lesson.get('smallest_experiment')}")
        except Exception:
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    return row
