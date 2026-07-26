"""Primary metric: bench pass_rate + quiz + staleness."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
BENCH_DIR = ROOT / "memory" / "bench"
HEALTH_PATH = BENCH_DIR / "health.json"


def _parse_ts(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


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
    qpath = ROOT / "memory" / "quiz" / "latest.json"
    if qpath.exists():
        try:
            quiz = json.loads(qpath.read_text(encoding="utf-8"))
        except Exception:
            pass

    now = datetime.now(timezone.utc)
    bench_ts = _parse_ts(latest.get("timestamp"))
    stale_hours = None
    stale = True
    if bench_ts:
        stale_hours = round((now - bench_ts).total_seconds() / 3600.0, 2)
        stale = stale_hours > 24.0

    healthy = pass_rate >= 0.4 and not bool(guardian.get("frozen")) and not stale

    out = {
        "primary_metric": "bench_pass_rate",
        "pass_rate": round(pass_rate, 3),
        "pass_rate_avg7": round(avg7, 3),
        "latency_s_avg7": round(avg_latency, 2),
        "quiz_pass_rate": quiz.get("pass_rate"),
        "quiz_n": quiz.get("n"),
        "healthy": healthy,
        "stale": stale,
        "stale_hours": stale_hours,
        "guardian_frozen": bool(guardian.get("frozen")),
        "guardian_reason": guardian.get("reason"),
        "updated_at": now.isoformat(),
    }
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    HEALTH_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out
