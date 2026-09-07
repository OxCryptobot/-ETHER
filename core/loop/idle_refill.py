"""F12: when pending is empty and live honest < target, write next FAST envelope."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[2]).resolve()
PENDING = ROOT / "artifacts" / "jobs" / "pending"
OUT = ROOT / "artifacts" / "idle_refill.json"
TARGET = float(os.getenv("ETHER_HONEST_LIVE_TARGET", "0.99"))


def _live_rate() -> float:
    p = ROOT / "artifacts" / "honest_live.json"
    if not p.exists():
        p = ROOT / "artifacts" / "measure_tick.json"
        if not p.exists():
            return 0.0
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            steps = data.get("steps") or {}
            hl = (steps.get("honest_live") or {})
            return float(hl.get("live_honest_rate") or 0.0)
        except Exception:
            return 0.0
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return float(data.get("live_honest_rate") or data.get("rate") or 0.0)
    except Exception:
        return 0.0


def pending_jobs() -> list[str]:
    if not PENDING.exists():
        return []
    return [p.name for p in PENDING.glob("*.json") if p.name != ".gitkeep"]


def propose() -> Dict[str, Any]:
    jobs = pending_jobs()
    rate = _live_rate()
    should = (not jobs) and rate < TARGET
    payload = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "pending_n": len(jobs),
        "live_honest_rate": rate,
        "target": TARGET,
        "should_refill": should,
        "note": "FAST refill only. Does not fake unaided LIVE. Dual chat locked.",
    }
    if should:
        payload["next"] = {
            "id": "idle_gate_sample",
            "class": "fast",
            "steps": [
                {
                    "argv": [
                        ".venv/Scripts/python.exe",
                        "-m",
                        "pytest",
                        "tests/test_live_criteria.py",
                        "-q",
                        "--tb=short",
                    ],
                    "timeout": 90,
                }
            ],
        }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(propose(), indent=2))
