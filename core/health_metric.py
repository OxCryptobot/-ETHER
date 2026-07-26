"""Primary metric: bench + quiz + dual staleness. Daemon uses declare_healthy()."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
BENCH_DIR = ROOT / "memory" / "bench"
QUIZ_DIR = ROOT / "memory" / "quiz"
HEALTH_PATH = BENCH_DIR / "health.json"
STALE_HOURS = 24.0


def _parse_ts(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _hours_since(ts: Optional[str]) -> Optional[float]:
    dt = _parse_ts(ts)
    if not dt:
        return None
    return round((datetime.now(timezone.utc) - dt).total_seconds() / 3600.0, 2)


def compute_health() -> Dict[str, Any]:
    latest: Dict[str, Any] = {}
    path = BENCH_DIR / "latest.json"
    if path.exists():
        try:
            latest = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            latest = {}

    rates: List[float] = []
    latencies: List[float] = []
    for p in sorted(BENCH_DIR.glob("bench_*.json"))[-14:]:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("pass_rate") is not None:
                rates.append(float(d["pass_rate"]))
            if d.get("duration_s") is not None:
                latencies.append(float(d["duration_s"]))
        except Exception:
            continue

    pass_rate = float(
        latest.get("pass_rate") if latest.get("pass_rate") is not None else (rates[-1] if rates else 0.0)
    )
    avg7 = sum(rates[-7:]) / len(rates[-7:]) if rates else pass_rate
    avg_latency = sum(latencies[-7:]) / len(latencies[-7:]) if latencies else float(latest.get("duration_s") or 0.0)

    guardian: Dict[str, Any] = {}
    gpath = BENCH_DIR / "guardian.json"
    if gpath.exists():
        try:
            guardian = json.loads(gpath.read_text(encoding="utf-8"))
        except Exception:
            pass

    quiz: Dict[str, Any] = {}
    qpath = QUIZ_DIR / "latest.json"
    if qpath.exists():
        try:
            quiz = json.loads(qpath.read_text(encoding="utf-8"))
        except Exception:
            pass

    bench_stale_h = _hours_since(latest.get("timestamp"))
    quiz_stale_h = _hours_since(quiz.get("timestamp"))
    bench_stale = bench_stale_h is None or bench_stale_h > STALE_HOURS
    quiz_stale = quiz_stale_h is None or quiz_stale_h > STALE_HOURS
    stale = bench_stale or quiz_stale

    reasons: List[str] = []
    if bench_stale:
        reasons.append(f"bench_stale:{bench_stale_h}h" if bench_stale_h is not None else "bench_missing")
    if quiz_stale:
        reasons.append(f"quiz_stale:{quiz_stale_h}h" if quiz_stale_h is not None else "quiz_missing")
    if pass_rate < 0.4:
        reasons.append(f"pass_rate_low:{pass_rate}")
    if guardian.get("frozen"):
        reasons.append(f"guardian:{guardian.get('reason')}")

    healthy = (
        pass_rate >= 0.4
        and not bool(guardian.get("frozen"))
        and not bench_stale
        and not quiz_stale
    )

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
    """Daemon gate: only True when bench+quiz fresh and not frozen."""
    h = compute_health()
    return {
        "healthy": bool(h.get("healthy")),
        "reasons": list(h.get("unhealthy_reasons") or []),
        "pass_rate": h.get("pass_rate"),
        "quiz_pass_rate": h.get("quiz_pass_rate"),
        "stale": h.get("stale"),
    }
