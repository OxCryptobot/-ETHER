"""Batch queue + autonomy telemetry for dashboard snapshot."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]


def collect_batch_autonomy() -> Dict[str, Any]:
    out: Dict[str, Any] = {"batch": {}, "autonomy": {}}
    try:
        from core.batch_queue import status

        out["batch"] = status()
    except Exception as e:
        out["batch"] = {"error": str(e)[:120]}

    # recent autonomy log tail
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

    # healthy flag
    hf = ROOT / "memory" / "daemon" / "healthy.json"
    if hf.exists():
        try:
            import json

            out["daemon_healthy"] = json.loads(hf.read_text(encoding="utf-8"))
        except Exception:
            out["daemon_healthy"] = {}
    return out
