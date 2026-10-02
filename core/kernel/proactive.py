"""Notice one real failure and queue one retry. Never a second writer, never a model call."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def _load(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _argv(job: Dict[str, Any]) -> List[str]:
    steps = job.get("steps") or []
    if not steps or not isinstance(steps[0], dict):
        return []
    return [str(x) for x in (steps[0].get("argv") or [])]


def act(root: Path) -> Dict[str, Any]:
    root = Path(root)
    failed_dir = root / "artifacts" / "jobs" / "failed"
    pending = root / "artifacts" / "jobs" / "pending"
    done_path = root / "artifacts" / "proactive_done.json"
    done = set(_load(done_path).get("ids") or [])
    row: Dict[str, Any] = {"ok": True, "queued": False}
    if not failed_dir.is_dir():
        return row
    from core.kernel.argv_allow import argv_allowed

    newest = sorted(failed_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in newest:
        job = _load(path)
        jid = str(job.get("id") or path.stem)
        if not jid or jid in done or jid.startswith("retry_"):
            continue
        argv = _argv(job)
        if not argv_allowed(argv):
            continue
        retry_id = "retry_" + jid
        dest = pending / f"{retry_id}.json"
        if dest.exists():
            row["note"] = "already_pending"
            return row
        pending.mkdir(parents=True, exist_ok=True)
        job["id"] = retry_id
        job["note"] = "proactive retry of " + jid
        dest.write_text(json.dumps(job, indent=2) + "\n", encoding="utf-8")
        done.add(jid)
        done_path.parent.mkdir(parents=True, exist_ok=True)
        done_path.write_text(json.dumps({"ids": sorted(done)}, indent=2) + "\n", encoding="utf-8")
        try:
            from core.kernel.edit_memory import remember
            remember(root, f"retry queued for {jid}")
        except Exception:
            pass
        row.update({"queued": True, "id": retry_id, "of": jid})
        return row
    return row
