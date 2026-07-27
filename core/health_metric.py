"""Primary metric: bench + quiz + dual staleness. Daemon uses declare_healthy().

This gate used to fail OPEN on every absurd input it was handed:

  * a bench/quiz timestamp in the FUTURE produced `stale_hours: -8760` and
    `healthy: True` — the freshness test was `hours > 24`, and -8760 is not.
  * a bench file with no `pass_rate` key silently fell back to an older
    bench_*.json, so a broken/truncated run inherited yesterday's score.
  * `quiz.pass_rate == 0.0` was healthy, because only the bench rate was gated.

It also read a CACHED memory/bench/guardian.json instead of calling
`bench_guardian.evaluate()`, so health was order-dependent: whether the system
looked frozen depended on whether something else happened to call `is_frozen()`
first in the same process.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
BENCH_DIR = ROOT / "memory" / "bench"
QUIZ_DIR = ROOT / "memory" / "quiz"
HEALTH_PATH = BENCH_DIR / "health.json"
STALE_HOURS = 24.0
# Tolerated clock skew; beyond it a "future" stamp is not evidence.
CLOCK_SKEW_TOL_H = 0.25


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


def _hours_since(ts: Optional[str]) -> Optional[float]:
    dt = _parse_ts(ts)
    if not dt:
        return None
    return round((datetime.now(timezone.utc) - dt).total_seconds() / 3600.0, 2)


def _freshness(label: str, ts: Optional[str]) -> Tuple[Optional[float], bool, Optional[str]]:
    """(age_hours, stale, reason). A future stamp is stale, not fresh."""
    hours = _hours_since(ts)
    if hours is None:
        return None, True, f"{label}_missing"
    if hours < -CLOCK_SKEW_TOL_H:
        return hours, True, f"{label}_timestamp_in_future:{abs(hours)}h"
    if hours > STALE_HOURS:
        return hours, True, f"{label}_stale:{hours}h"
    return hours, False, None


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


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _guardian_decision() -> Dict[str, Any]:
    """Live guardian verdict, not the cached file.

    Falling back to the cached file only when evaluate() itself raises keeps
    this readable offline, but a stale cache must never be the primary source.
    """
    try:
        from core.bench_guardian import evaluate

        decision = evaluate() or {}
        if isinstance(decision, dict):
            return decision
    except Exception as e:  # pragma: no cover - defensive
        cached = _read_json(BENCH_DIR / "guardian.json")
        cached.setdefault("reason", f"guardian_error:{str(e)[:80]}")
        return cached
    return _read_json(BENCH_DIR / "guardian.json")


def compute_health() -> Dict[str, Any]:
    latest = _read_json(BENCH_DIR / "latest.json")
    bench_present = bool(latest)

    rates: List[float] = []
    latencies: List[float] = []
    for p in sorted(BENCH_DIR.glob("bench_*.json"))[-14:]:
        d = _read_json(p)
        r = _rate_of(d)
        if r is not None:
            rates.append(r)
        if d.get("duration_s") is not None:
            try:
                latencies.append(float(d["duration_s"]))
            except (TypeError, ValueError):
                pass

    bench_rate = _rate_of(latest) if bench_present else None
    # Reported number may fall back to history, but the GATE below never does:
    # a bench without a usable pass_rate is not evidence of health.
    pass_rate = bench_rate if bench_rate is not None else (rates[-1] if rates else 0.0)
    avg7 = sum(rates[-7:]) / len(rates[-7:]) if rates else pass_rate
    try:
        fallback_latency = float(latest.get("duration_s") or 0.0)
    except (TypeError, ValueError):
        fallback_latency = 0.0
    avg_latency = sum(latencies[-7:]) / len(latencies[-7:]) if latencies else fallback_latency

    guardian = _guardian_decision()
    quiz = _read_json(QUIZ_DIR / "latest.json")
    quiz_present = bool(quiz)
    quiz_rate = _rate_of(quiz) if quiz_present else None

    bench_stale_h, bench_stale, bench_reason = _freshness("bench", latest.get("timestamp"))
    quiz_stale_h, quiz_stale, quiz_reason = _freshness("quiz", quiz.get("timestamp"))
    if not bench_present:
        bench_stale, bench_reason = True, "bench_missing"
    if not quiz_present:
        quiz_stale, quiz_reason = True, "quiz_missing"
    stale = bench_stale or quiz_stale

    bench_min = float(os.getenv("ETHER_BENCH_MIN_PASS", "0.40"))
    quiz_min = float(os.getenv("ETHER_QUIZ_MIN_PASS", "0.40"))

    reasons: List[str] = []
    if bench_reason:
        reasons.append(bench_reason)
    if quiz_reason:
        reasons.append(quiz_reason)
    if bench_present and bench_rate is None:
        reasons.append("bench_pass_rate_missing_or_invalid")
    if bench_rate is not None and bench_rate < bench_min:
        reasons.append(f"pass_rate_low:{bench_rate}")
    if quiz_present and quiz_rate is None:
        reasons.append("quiz_pass_rate_missing_or_invalid")
    if quiz_rate is not None and quiz_rate < quiz_min:
        reasons.append(f"quiz_pass_rate_low:{quiz_rate}")
    if guardian.get("frozen"):
        reasons.append(f"guardian:{guardian.get('reason')}")

    healthy = not reasons

    out = {
        "primary_metric": "bench_pass_rate",
        "pass_rate": round(pass_rate, 3),
        "pass_rate_avg7": round(avg7, 3),
        "latency_s_avg7": round(avg_latency, 2),
        "quiz_pass_rate": quiz.get("pass_rate"),
        "quiz_n": quiz.get("n"),
        "healthy": healthy,
        "stale": stale,
        "bench_stale": bench_stale,
        "quiz_stale": quiz_stale,
        "stale_hours": bench_stale_h,
        "quiz_stale_hours": quiz_stale_h,
        "unhealthy_reasons": reasons,
        "guardian_frozen": bool(guardian.get("frozen")),
        "guardian_reason": guardian.get("reason"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    HEALTH_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def declare_healthy() -> Dict[str, Any]:
    """Daemon gate: only True when bench+quiz fresh, scored, and not frozen.

    NOTE for callers: this RETURNS a verdict, it does not enforce one. A caller
    that logs the result and then does the work anyway has no gate. See
    scripts/ether_daemon.py::flywheel_loop.
    """
    h = compute_health()
    return {
        "healthy": bool(h.get("healthy")),
        "reasons": list(h.get("unhealthy_reasons") or []),
        "pass_rate": h.get("pass_rate"),
        "quiz_pass_rate": h.get("quiz_pass_rate"),
        "stale": h.get("stale"),
    }
