"""Moonshot 11 — Latency SLO panel.

p50/p95 for scripted vs live vs tool_runtime. Alerts when live p95 > 10x scripted.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "latency_slo.json"
ALERT_RATIO = float(os.getenv("ETHER_LATENCY_ALERT_RATIO", "10"))


def _pct(vals: List[float], p: float) -> Optional[float]:
    if not vals:
        return None
    s = sorted(vals)
    if len(s) == 1:
        return round(s[0], 3)
    k = (len(s) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return round(s[f], 3)
    return round(s[f] + (s[c] - s[f]) * (k - f), 3)


def _dur(row: Dict[str, Any]) -> Optional[float]:
    for k in ("duration_s", "elapsed_s", "latency_s", "wall_s", "seconds"):
        v = row.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return None


def compute() -> Dict[str, Any]:
    from core.honest_live import collect_scoreboard_rows, classify_row

    rows = collect_scoreboard_rows()
    scripted: List[float] = []
    live: List[float] = []
    tool_rt: List[float] = []
    for r in rows:
        d = _dur(r)
        if d is None or d <= 0:
            continue
        c = classify_row(r)
        mode = str(r.get("mode") or "").lower()
        strat = str(r.get("strategy") or "").lower()
        if mode == "scripted" or "scripted" in strat:
            scripted.append(d)
        if c.get("live"):
            live.append(d)
        if "tool_runtime" in strat or c.get("toolish"):
            tool_rt.append(d)

    def bucket(vals: List[float]) -> Dict[str, Any]:
        return {
            "n": len(vals),
            "p50": _pct(vals, 50),
            "p95": _pct(vals, 95),
            "max": round(max(vals), 3) if vals else None,
        }

    sb, lb, tb = bucket(scripted), bucket(live), bucket(tool_rt)
    ratio = None
    alert = False
    if sb.get("p95") and lb.get("p95") and sb["p95"] > 0:
        ratio = round(lb["p95"] / sb["p95"], 2)
        alert = ratio > ALERT_RATIO

    payload = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "scripted": sb,
        "live": lb,
        "tool_runtime": tb,
        "live_over_scripted_p95": ratio,
        "alert_ratio_threshold": ALERT_RATIO,
        "alert": alert,
        "note": "Alert when live p95 > Nx scripted p95",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
