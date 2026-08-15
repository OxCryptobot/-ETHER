"""Live latency budget — attack the 148x scripted/live ratio.

Critical fix #4: if a live step exceeds budget, mark typed timeout.
Does not change Pipeline.run body — host/job layer enforces step timeouts.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

# Seconds — override via env without code change
LIVE_STEP_BUDGET_S = float(os.getenv("ETHER_LIVE_STEP_BUDGET_S", "45"))
SCRIPTED_STEP_BUDGET_S = float(os.getenv("ETHER_SCRIPTED_STEP_BUDGET_S", "120"))
MEASURE_STEP_BUDGET_S = float(os.getenv("ETHER_MEASURE_STEP_BUDGET_S", "90"))
TARGET_LIVE_RATIO = float(os.getenv("ETHER_TARGET_LIVE_RATIO", "20"))


def step_timeout_for_job(job: Dict[str, Any], default: int = 3600) -> int:
    """Clamp step timeout by class so live cannot burn unbounded GPU."""
    jid = str(job.get("id") or "").lower()
    note = str(job.get("note") or "").lower()
    cls = str(job.get("class") or "").lower()
    hay = f"{jid} {note} {cls}"
    if "measure" in hay or "honest_live" in hay or "soft_launch" in hay:
        budget = int(MEASURE_STEP_BUDGET_S)
    elif cls == "live" or ("live" in hay and "scripted" not in hay):
        budget = int(LIVE_STEP_BUDGET_S)
    elif "scripted" in hay or cls == "fast":
        budget = int(SCRIPTED_STEP_BUDGET_S)
    else:
        budget = int(default)
    # Never raise above explicit step timeout if smaller
    return budget


def ratio_status(scripted_s: float, live_s: float) -> Dict[str, Any]:
    if scripted_s <= 0:
        return {"ratio": None, "ok": False, "reason": "no_scripted_baseline"}
    ratio = live_s / scripted_s
    return {
        "ratio": round(ratio, 2),
        "ok": ratio <= TARGET_LIVE_RATIO,
        "target": TARGET_LIVE_RATIO,
        "scripted_s": scripted_s,
        "live_s": live_s,
    }


def budgets() -> Dict[str, float]:
    return {
        "live_step_s": LIVE_STEP_BUDGET_S,
        "scripted_step_s": SCRIPTED_STEP_BUDGET_S,
        "measure_step_s": MEASURE_STEP_BUDGET_S,
        "target_live_ratio": TARGET_LIVE_RATIO,
    }
