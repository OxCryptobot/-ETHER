"""Bench guardian — freeze risky autonomy if regression detected.

Failure mode this module defends against: promote/fabricate keep running on
evidence that no longer exists. Two ways that used to happen silently:

  * the baseline drifted DOWN. `maybe_reset_baseline_on_recovery()` rewrote
    baseline.json to whatever the current rate was, as long as the single-step
    drop was inside the 0.10 tolerance, so 0.95 -> 0.86 -> 0.77 -> ... -> 0.41
    never tripped the guardian: every individual step was "within tolerance".
    The baseline now only ratchets UP; lowering it needs `set_baseline(...,
    allow_lower=True)`, i.e. an explicit operator action.
  * the guardian failed OPEN. No bench at all returned ok=True/"no_bench_yet",
    and the bench timestamp was never read, so a 400-day-old pass_rate=0.99
    kept everything unfrozen forever. Absence and staleness now freeze.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
BENCH_LATEST = ROOT / "memory" / "bench" / "latest.json"
GUARD_PATH = ROOT / "memory" / "bench" / "guardian.json"
BASELINE_PATH = ROOT / "memory" / "bench" / "baseline.json"

# A bench older than this cannot vouch for the current system.
DEFAULT_MAX_BENCH_AGE_H = 72.0
# Tolerated clock skew; beyond it a "future" bench is a broken clock or a
# hand-edited file, not evidence.
CLOCK_SKEW_TOL_H = 0.25


def guardian_enabled() -> bool:
    return os.getenv("ETHER_BENCH_GUARDIAN", "1") == "1"


def max_bench_age_h() -> float:
    try:
        return float(os.getenv("ETHER_BENCH_MAX_AGE_H", str(DEFAULT_MAX_BENCH_AGE_H)))
    except Exception:
        return DEFAULT_MAX_BENCH_AGE_H


def _parse_ts(ts: Optional[str]) -> Optional[datetime]:
    if not ts or not isinstance(ts, str):
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def bench_age_hours(latest: Dict[str, Any]) -> Optional[float]:
    """Hours since the bench ran; None when unstamped/unparseable.

    Negative means the stamp is in the future (bad clock or edited file).
    """
    dt = _parse_ts((latest or {}).get("timestamp"))
    if dt is None:
        return None
    return round((datetime.now(timezone.utc) - dt).total_seconds() / 3600.0, 2)


def load_latest() -> Optional[Dict[str, Any]]:
    if not BENCH_LATEST.exists():
        return None
    try:
        data = json.loads(BENCH_LATEST.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def load_baseline() -> Optional[Dict[str, Any]]:
    if not BASELINE_PATH.exists():
        return None
    try:
        data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _write_baseline(base: Dict[str, Any]) -> Dict[str, Any]:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(base, indent=2), encoding="utf-8")
    return base


def _rate_of(payload: Dict[str, Any]) -> Optional[float]:
    """Numeric pass_rate in [0, 1], or None when missing/absurd."""
    raw = (payload or {}).get("pass_rate")
    if raw is None or isinstance(raw, bool):
        return None
    try:
        rate = float(raw)
    except (TypeError, ValueError):
        return None
    if rate != rate or rate < 0.0 or rate > 1.0:  # NaN or out of range
        return None
    return rate


def ensure_baseline(latest: Dict[str, Any]) -> Dict[str, Any]:
    """Baseline = best pass_rate ever observed. Ratchets up, never down.

    The old version pinned the baseline to the first bench it ever saw and
    never raised it, so a system that grew 0.42 -> 0.95 could fall back to 0.43
    and still read as "healthy" against a 0.42 baseline.
    """
    latest_rate = _rate_of(latest)
    base = load_baseline()
    now = datetime.now(timezone.utc).isoformat()

    if base is None:
        return _write_baseline(
            {
                "pass_rate": latest_rate if latest_rate is not None else 0.0,
                "n": (latest or {}).get("n"),
                "set_at": now,
                "source": "first_bench",
            }
        )

    current = _rate_of(base) or 0.0
    if latest_rate is not None and latest_rate > current:
        return _write_baseline(
            {
                **base,
                "pass_rate": latest_rate,
                "n": (latest or {}).get("n"),
                "previous_pass_rate": current,
                "raised_at": now,
                "set_at": base.get("set_at") or now,
                "source": "ratchet_up",
            }
        )
    # Never lower it here: see set_baseline() for the operator path.
    base.setdefault("pass_rate", current)
    return base


def set_baseline(
    pass_rate: float,
    *,
    n: Any = None,
    reason: str = "manual",
    allow_lower: bool = False,
) -> Dict[str, Any]:
    """Explicit operator action. Lowering requires allow_lower=True.

    Automation must never call this with allow_lower=True; that is the ratchet
    the regression guardian depends on.
    """
    try:
        rate = float(pass_rate)
    except (TypeError, ValueError):
        return {"ok": False, "reason": "pass_rate_not_numeric"}
    if rate < 0.0 or rate > 1.0:
        return {"ok": False, "reason": f"pass_rate {rate} out of range"}

    base = load_baseline() or {}
    current = _rate_of(base) or 0.0
    if rate < current and not allow_lower:
        return {
            "ok": False,
            "reason": f"refusing to lower baseline {current:.3f} -> {rate:.3f} without allow_lower",
            "baseline": base,
        }
    new = _write_baseline(
        {
            "pass_rate": rate,
            "n": n,
            "previous_pass_rate": current,
            "set_at": datetime.now(timezone.utc).isoformat(),
            "source": f"operator:{reason}"[:120],
            "lowered": rate < current,
        }
    )
    return {"ok": True, "baseline": new}


def _freeze_reasons(latest: Dict[str, Any]) -> Tuple[List[str], Optional[float], Optional[float]]:
    reasons: List[str] = []
    rate = _rate_of(latest)
    age_h = bench_age_hours(latest)

    if rate is None:
        reasons.append("bench pass_rate missing or not a number in [0,1]")
    else:
        min_rate = float(os.getenv("ETHER_BENCH_MIN_PASS", "0.40"))
        if rate < min_rate:
            reasons.append(f"pass_rate {rate:.3f} < min {min_rate}")

    if age_h is None:
        reasons.append("bench has no usable timestamp")
    elif age_h < -CLOCK_SKEW_TOL_H:
        reasons.append(f"bench timestamp is {abs(age_h):.2f}h in the future")
    elif age_h > max_bench_age_h():
        reasons.append(f"bench stale {age_h:.2f}h > max {max_bench_age_h():.2f}h")

    return reasons, rate, age_h


def evaluate() -> Dict[str, Any]:
    """Return guardian decision. ok=False means freeze promote/fabricate.

    Fails CLOSED: no bench, an unstamped/stale/future-dated bench, or a bench
    with no usable pass_rate all freeze.
    """
    if not guardian_enabled():
        return {"ok": True, "frozen": False, "reason": "guardian_disabled"}

    latest = load_latest()
    if not latest:
        decision = {
            "ok": False,
            "frozen": True,
            "reason": "no_bench_yet — guardian fails closed until a bench exists",
            "reasons": ["no bench result on disk"],
            "pass_rate": None,
            "baseline": None,
            "bench_age_h": None,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        _save(decision)
        return decision

    base = ensure_baseline(latest)
    baseline = _rate_of(base) or 0.0
    drop_tol = float(os.getenv("ETHER_BENCH_DROP_TOL", "0.10"))

    reasons, rate, age_h = _freeze_reasons(latest)
    if rate is not None and baseline > 0 and (baseline - rate) > drop_tol:
        reasons.append(f"regression {baseline:.3f} -> {rate:.3f} exceeds tol {drop_tol}")

    frozen = bool(reasons)
    decision = {
        "ok": not frozen,
        "frozen": frozen,
        "reason": "; ".join(reasons) if reasons else "healthy",
        "reasons": reasons,
        "pass_rate": rate,
        "baseline": baseline,
        "n": latest.get("n"),
        "bench_timestamp": latest.get("timestamp"),
        "bench_age_h": age_h,
        "max_bench_age_h": max_bench_age_h(),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    _save(decision)
    return decision


def _save(decision: Dict[str, Any]) -> None:
    GUARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    GUARD_PATH.write_text(json.dumps(decision, indent=2), encoding="utf-8")


def is_frozen() -> bool:
    d = evaluate()
    return bool(d.get("frozen"))
