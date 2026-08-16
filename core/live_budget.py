"""Phase 1D — Live wall-time budget.

Training wheels stay ON. This does not enable soft launch.
It only defines hard ceilings so live experiments die fast instead of
burning 10–15 minutes on tool_runtime_failed_terminal.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "live_budget.json"

# Defaults sized for GTX 1650 / 4B host — override via env
DEFAULT_MAX_WALL_S = int(os.getenv("ETHER_LIVE_MAX_WALL_S", "90"))
DEFAULT_MAX_STEPS = int(os.getenv("ETHER_LIVE_MAX_STEPS", "12"))
DEFAULT_STEP_TIMEOUT_S = int(os.getenv("ETHER_LIVE_STEP_TIMEOUT_S", "25"))


def limits() -> Dict[str, Any]:
    wheels = (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0"
    return {
        "updated": datetime.now(timezone.utc).isoformat(),
        "training_wheels": wheels,
        "max_wall_s": DEFAULT_MAX_WALL_S,
        "max_steps": DEFAULT_MAX_STEPS,
        "step_timeout_s": DEFAULT_STEP_TIMEOUT_S,
        "live_enqueue_allowed": not wheels,
        "note": (
            "While wheels ON, live enqueue remains blocked by host policy. "
            "These ceilings apply if a live job is forced for measurement."
        ),
    }


def publish() -> Dict[str, Any]:
    payload = limits()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


def apply_to_job(job: Dict[str, Any]) -> Dict[str, Any]:
    """Clamp live job step timeouts — never raises; never lifts wheels."""
    lim = limits()
    out = dict(job)
    if str(out.get("class") or "").lower() != "live" and "live" not in str(
        out.get("note") or ""
    ).lower():
        return out
    steps = []
    for step in out.get("steps") or []:
        if not isinstance(step, dict):
            steps.append(step)
            continue
        s = dict(step)
        t = int(s.get("timeout") or lim["max_wall_s"])
        s["timeout"] = min(t, lim["max_wall_s"])
        steps.append(s)
    out["steps"] = steps
    out["live_budget"] = {
        "max_wall_s": lim["max_wall_s"],
        "max_steps": lim["max_steps"],
        "step_timeout_s": lim["step_timeout_s"],
    }
    return out


if __name__ == "__main__":
    print(json.dumps(publish(), indent=2))
