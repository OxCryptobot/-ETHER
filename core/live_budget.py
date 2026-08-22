"""Phase 1D — Live wall-time budget.

Training wheels stay ON. This does not enable soft launch.
It only defines hard ceilings so live experiments die fast instead of
burning 10–15 minutes on tool_runtime_failed_terminal.

2026-08-22: Measurement path (gate_sample / controlled live) gets a
higher ceiling so the only approved under-wheels measurement can finish
and produce countable rows. Production LIVE stays tight.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "live_budget.json"

# Production LIVE ceilings (GTX 1650 / 4B host)
DEFAULT_MAX_WALL_S = int(os.getenv("ETHER_LIVE_MAX_WALL_S", "90"))
DEFAULT_MAX_STEPS = int(os.getenv("ETHER_LIVE_MAX_STEPS", "12"))
DEFAULT_STEP_TIMEOUT_S = int(os.getenv("ETHER_LIVE_STEP_TIMEOUT_S", "25"))

# Measurement / gate_sample ceilings — room for one easy fixture under 4B
MEASURE_MAX_WALL_S = int(os.getenv("ETHER_MEASURE_MAX_WALL_S", "300"))
MEASURE_MAX_STEPS = int(os.getenv("ETHER_MEASURE_MAX_STEPS", "10"))
MEASURE_STEP_TIMEOUT_S = int(os.getenv("ETHER_MEASURE_STEP_TIMEOUT_S", "50"))


def _is_measurement(job: Dict[str, Any]) -> bool:
    """True for the approved under-wheels measurement path."""
    cls = str(job.get("class") or "").strip().lower()
    note = str(job.get("note") or "").lower()
    jid = str(job.get("id") or "").lower()
    hay = f"{cls} {note} {jid}"
    return (
        cls in ("gate_sample", "measure")
        or "gate_sample" in hay
        or "eligible_live" in hay
        or "controlled live" in hay
        or "controlled_live" in hay
    )


def limits(*, measurement: bool = False) -> Dict[str, Any]:
    wheels = (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0"
    if measurement:
        return {
            "updated": datetime.now(timezone.utc).isoformat(),
            "training_wheels": wheels,
            "max_wall_s": MEASURE_MAX_WALL_S,
            "max_steps": MEASURE_MAX_STEPS,
            "step_timeout_s": MEASURE_STEP_TIMEOUT_S,
            "live_enqueue_allowed": not wheels,
            "budget_class": "measurement",
            "note": (
                "Measurement budget for gate_sample / controlled live under wheels. "
                "Production LIVE remains at the tighter default."
            ),
        }
    return {
        "updated": datetime.now(timezone.utc).isoformat(),
        "training_wheels": wheels,
        "max_wall_s": DEFAULT_MAX_WALL_S,
        "max_steps": DEFAULT_MAX_STEPS,
        "step_timeout_s": DEFAULT_STEP_TIMEOUT_S,
        "live_enqueue_allowed": not wheels,
        "budget_class": "production",
        "note": (
            "While wheels ON, live enqueue remains blocked by host policy. "
            "These ceilings apply if a live job is forced for measurement."
        ),
    }


def publish() -> Dict[str, Any]:
    payload = limits()
    payload["measurement"] = limits(measurement=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


def apply_to_job(job: Dict[str, Any]) -> Dict[str, Any]:
    """Clamp step timeouts — never raises; never lifts wheels.

    Measurement jobs (gate_sample) receive the higher ceiling so the
    approved under-wheels path can actually finish and produce rows.
    """
    is_meas = _is_measurement(job)
    lim = limits(measurement=is_meas)
    out = dict(job)

    cls = str(out.get("class") or "").lower()
    note = str(out.get("note") or "").lower()
    if cls not in ("live", "gate_sample", "measure") and "live" not in note:
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
        "budget_class": lim.get("budget_class", "production"),
    }
    return out


if __name__ == "__main__":
    print(json.dumps(publish(), indent=2))
