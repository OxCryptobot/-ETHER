"""One primary metric: bench pass_rate (+ latency secondary)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
BENCH_DIR = ROOT / "memory" / "bench"
HEALTH_PATH = BENCH_DIR / "health.json"


def compute_health() -> Dict[str, Any]:
    latest = {}
    path = BENCH_DIR / "latest.json"
    if path.exists():
        try:
            latest = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            latest = {}

    # rolling from history files
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

    pass_rate = float(latest.get("pass_rate") if latest.get("pass_rate") is not None else (rates[-1] if rates else 0.0))
    avg7 = sum(rates[-7:]) / len(rates[-7:]) if rates else pass_rate
    avg_latency = sum(latencies[-7:]) / len(latencies[-7:]) if latencies else float(latest.get("duration_s") or 0.0)

    guardian = {}
    gpath = BENCH_DIR / "guardian.json"
    if gpath.exists():
        try:
            guardian = json.loads(gpath.read_text(encoding="utf-8"))
        except Exception:
            pass

    healthy = pass_rate >= 0.4 and not bool(guardian.get("frozen"))
    out = {
        "primary_metric": "bench_pass_rate",
        "pass_rate": round(pass_rate, 3),
        "pass_rate_avg7": round(avg7, 3),
        "latency_s_avg7": round(avg_latency, 2),
        "healthy": healthy,
        "guardian_frozen": bool(guardian.get("frozen")),
        "guardian_reason": guardian.get("reason"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    HEALTH_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out
