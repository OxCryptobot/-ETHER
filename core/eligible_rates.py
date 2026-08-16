"""Eligible-set rates — denylist fixtures excluded from live KPIs.

Phase 1 critical: stop treating projected denylist success as measured skill.
Raw rates remain elsewhere; soft launch must use eligible rates when available.
Does not lift wheels. Does not enqueue LIVE.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Set

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "eligible_rates.json"
TIMEOUT_FLOOR_S = float(os.getenv("ETHER_TIMEOUT_FLOOR_S", "120"))


def _deny() -> Set[str]:
    try:
        from core.live_fixture_policy import deny_set

        return {d.lower() for d in deny_set() if d}
    except Exception:
        return {"ledger", "lru", "topo", "intervals", "pipeline_ledger"}


def _is_denied(row: Dict[str, Any], denied: Set[str]) -> bool:
    hay = " ".join(
        str(row.get(k) or "") for k in ("fixture", "name", "id", "strategy", "note")
    ).lower()
    return any(d and d in hay for d in denied)


def _is_timeout(row: Dict[str, Any], classified: Dict[str, Any]) -> bool:
    if classified.get("timeout"):
        return True
    ftype = str(row.get("failure_type") or "").lower()
    if "timeout" in ftype or "budget_exhaust" in ftype:
        return True
    try:
        dur = float(row.get("duration_s") or row.get("elapsed_s") or 0)
        if dur >= TIMEOUT_FLOOR_S and not classified.get("ok"):
            return True
    except Exception:
        pass
    return False


def compute() -> Dict[str, Any]:
    from core.honest_live import classify_row, collect_scoreboard_rows

    denied = _deny()
    rows = collect_scoreboard_rows()
    live_raw = 0
    live_eligible = 0
    timeout_raw = 0
    timeout_eligible = 0
    honest_eligible = 0
    ok_eligible = 0
    denied_live_n = 0

    for r in rows:
        c = classify_row(r)
        if not c.get("live"):
            continue
        live_raw += 1
        is_to = _is_timeout(r, c)
        if is_to:
            timeout_raw += 1
        if _is_denied(r, denied):
            denied_live_n += 1
            continue
        live_eligible += 1
        if is_to:
            timeout_eligible += 1
        if c.get("ok"):
            ok_eligible += 1
        if c.get("honest"):
            honest_eligible += 1

    def rate(n: int, d: int) -> Optional[float]:
        if d <= 0:
            return None
        return round(n / d, 4)

    raw_to = rate(timeout_raw, live_raw)
    elig_to = rate(timeout_eligible, live_eligible)
    elig_honest = rate(honest_eligible, live_eligible)

    timeout_eligible_ok = elig_to is not None and elig_to < 0.25
    honest_eligible_ok = elig_honest is not None and elig_honest >= 0.99

    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "denied": sorted(denied),
        "live_raw_n": live_raw,
        "live_eligible_n": live_eligible,
        "denied_live_n": denied_live_n,
        "timeout_raw_n": timeout_raw,
        "timeout_eligible_n": timeout_eligible,
        "timeout_rate_raw": raw_to,
        "timeout_rate_eligible": elig_to,
        "honest_eligible_n": honest_eligible,
        "ok_eligible_n": ok_eligible,
        "honest_rate_eligible": elig_honest,
        "target_timeout": 0.25,
        "target_honest": 0.99,
        "timeout_eligible_ok": timeout_eligible_ok,
        "honest_eligible_ok": honest_eligible_ok,
        "metrics_ok": bool(timeout_eligible_ok and honest_eligible_ok and live_eligible > 0),
        "wheels_must_stay_on": True,
        "soft_launch_blocked": True,
        "publish_ok": True,
        "ok": True,  # publish success — targets live in metrics_ok
        "note": (
            "Eligible = live rows not matching timeout denylist. "
            "Soft launch / wheels use eligible rates, never projected-only."
        ),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
