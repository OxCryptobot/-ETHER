"""Soft-launch readiness — measurement gate, not auto-promote.

Hard rule: soft_launch_ready is only True when rates exist, live rows exist,
honest rate meets threshold, AND ETHER_SOFT_LAUNCH=1 is explicitly set.
Prefers eligible-set rates (denylist excluded) when artifacts/eligible_rates.json
has live_eligible_n > 0. Default: blocked. Never auto-lifts wheels.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
RATES = ROOT / "artifacts" / "honest_live_rates.json"
ELIG = ROOT / "artifacts" / "eligible_rates.json"
SNAPSHOT = ROOT / "artifacts" / "phase3_snapshot.json"
OUT = ROOT / "artifacts" / "soft_launch_status.json"

DEFAULT_THRESHOLD = 0.99


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def evaluate(
    *,
    rates: Optional[Dict[str, Any]] = None,
    threshold: float = DEFAULT_THRESHOLD,
) -> Dict[str, Any]:
    rates = rates if rates is not None else _load(RATES)
    elig = _load(ELIG)
    snap = _load(SNAPSHOT)
    explicit = (os.getenv("ETHER_SOFT_LAUNCH") or "0").strip() == "1"
    wheels = (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0"

    # Prefer eligible-set when we have eligible live rows
    use_eligible = int(elig.get("live_eligible_n") or 0) > 0
    if use_eligible:
        live_n = int(elig.get("live_eligible_n") or 0)
        live_honest_rate = elig.get("honest_rate_eligible")
        timeout_rate = elig.get("timeout_rate_eligible")
        rate_source = "eligible"
    else:
        live_n = int(rates.get("live_n") or 0)
        live_honest_rate = rates.get("live_honest_rate")
        timeout_rate = None
        rate_source = "raw_honest_live"

    status = str(rates.get("status") or "missing_rates")
    blocked_reasons: list[str] = []

    if use_eligible:
        if not elig:
            blocked_reasons.append("no_eligible_rates_artifact")
    elif not rates:
        blocked_reasons.append("no_honest_live_rates_artifact")

    if live_n <= 0:
        blocked_reasons.append("no_live_rows")
    if live_honest_rate is None:
        blocked_reasons.append("live_honest_rate_unknown")
    elif float(live_honest_rate) < threshold:
        blocked_reasons.append(f"live_honest_rate_below_{threshold}")

    if timeout_rate is not None and float(timeout_rate) >= 0.25:
        blocked_reasons.append("timeout_rate_eligible_ge_0.25")

    if wheels:
        blocked_reasons.append("training_wheels_on")
    if not explicit:
        blocked_reasons.append("ETHER_SOFT_LAUNCH_not_1")

    ready = len(blocked_reasons) == 0
    payload: Dict[str, Any] = {
        "timestamp": _now(),
        "soft_launch_ready": ready,
        "soft_launch_blocked": not ready,
        "blocked_reasons": blocked_reasons,
        "threshold": threshold,
        "rates_status": status,
        "rate_source": rate_source,
        "live_n": live_n,
        "live_honest_rate": live_honest_rate,
        "timeout_rate_eligible": timeout_rate,
        "training_wheels": wheels,
        "explicit_flag": explicit,
        "snapshot_ok": bool(snap.get("ok")),
        "note": (
            "Ready only when eligible/raw rates green + wheels off + "
            "ETHER_SOFT_LAUNCH=1. This module never auto-lifts gates."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    import sys

    out = evaluate()
    print(json.dumps(out, indent=2))
    sys.exit(0)
