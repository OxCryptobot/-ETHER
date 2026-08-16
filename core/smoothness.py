"""Moonshot 25 — Single smoothness score 0–100 for machine health.

Phase 1D: timeout-inflated live latency is scored via live_timeout_rate,
not only the blended ratio.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "smoothness.json"


def compute() -> Dict[str, Any]:
    score = 100.0
    reasons = []

    try:
        from core.queue_governor import pending_count, MAX_PENDING

        depth = pending_count()
        if depth > MAX_PENDING:
            score -= 25
            reasons.append(f"queue_over_cap:{depth}")
        elif depth > MAX_PENDING * 0.75:
            score -= 12
            reasons.append(f"queue_high:{depth}")
        else:
            reasons.append(f"queue_ok:{depth}")
    except Exception as e:
        score -= 5
        reasons.append(f"queue_err:{e}")

    try:
        from core.honest_kpi import compute as kpi_compute

        kpi = kpi_compute()
        if kpi.get("tool_attempts", 0) == 0:
            score -= 15
            reasons.append("honest_unknown")
        elif (kpi.get("honest_rate") or 0) < 0.2:
            score -= 20
            reasons.append(f"honest_low:{kpi.get('primary_kpi')}")
        else:
            reasons.append(f"honest:{kpi.get('primary_kpi')}")
    except Exception:
        score -= 10
        reasons.append("honest_err")

    try:
        from core.latency_slo import compute as slo_compute

        slo = slo_compute()
        to_rate = slo.get("live_timeout_rate")
        ratio = slo.get("live_over_scripted_p95")
        ratio_all = slo.get("live_all_over_scripted_p95")
        if isinstance(to_rate, (int, float)):
            if to_rate >= 0.5:
                score -= 18
                reasons.append(f"timeout_rate_high:{to_rate}")
            elif to_rate >= 0.25:
                score -= 10
                reasons.append(f"timeout_rate:{to_rate}")
            else:
                reasons.append(f"timeout_rate_ok:{to_rate}")
        if slo.get("alert") and ratio is not None:
            score -= 12
            reasons.append(f"latency_alert:{ratio}")
        elif ratio is not None:
            reasons.append(f"latency_completed:{ratio}")
        if ratio_all is not None and ratio is not None and ratio_all != ratio:
            reasons.append(f"latency_all:{ratio_all}")
    except Exception:
        reasons.append("latency_unknown")

    cdir = ROOT / "artifacts" / "critiques"
    if cdir.exists():
        n = sum(1 for _ in cdir.glob("*.json"))
        if n > 30:
            score -= 10
            reasons.append(f"critique_backlog:{n}")
        elif n > 10:
            score -= 5
            reasons.append(f"critique_n:{n}")

    if (ROOT / "artifacts" / "steady_frozen.json").exists():
        score -= 25
        reasons.append("steady_frozen")

    score = max(0, min(100, round(score, 1)))
    grade = (
        "A"
        if score >= 85
        else "B"
        if score >= 70
        else "C"
        if score >= 50
        else "D"
        if score >= 30
        else "F"
    )
    payload = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "score": score,
        "grade": grade,
        "reasons": reasons,
        "note": "0-100 machine health; 1D timeout rate scored separately",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
