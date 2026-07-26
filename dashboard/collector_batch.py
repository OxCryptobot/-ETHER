"""Batch queue + autonomy telemetry for dashboard snapshot."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]


def _newest_heartbeat() -> Optional[str]:
    cands = []
    for rel in (
        "memory/daemon/heartbeat.txt",
        "memory/flywheel/heartbeat.txt",
    ):
        p = ROOT / rel
        if p.exists():
            try:
                t = p.read_text(encoding="utf-8").strip()
                if t:
                    cands.append((p.stat().st_mtime, t))
            except Exception:
                pass
    if not cands:
        return None
    cands.sort(key=lambda x: x[0], reverse=True)
    return cands[0][1]


def collect_batch_autonomy() -> Dict[str, Any]:
    out: Dict[str, Any] = {"batch": {}, "autonomy": {}}
    try:
        from core.batch_queue import status

        out["batch"] = status()
    except Exception as e:
        out["batch"] = {"error": str(e)[:120]}

    log_path = ROOT / "memory" / "daemon" / "autonomy.jsonl"
    events = []
    if log_path.exists():
        try:
            import json

            lines = log_path.read_text(encoding="utf-8").splitlines()[-15:]
            for line in lines:
                if line.strip():
                    try:
                        events.append(json.loads(line))
                    except Exception:
                        pass
        except Exception:
            pass
    out["autonomy"] = {
        "recent_events": list(reversed(events)),
        "last_event": events[-1] if events else None,
    }

    hf = ROOT / "memory" / "daemon" / "healthy.json"
    if hf.exists():
        try:
            import json

            out["daemon_healthy"] = json.loads(hf.read_text(encoding="utf-8"))
        except Exception:
            out["daemon_healthy"] = {}

    hb = _newest_heartbeat()
    if hb:
        out["heartbeat"] = hb
    return out
