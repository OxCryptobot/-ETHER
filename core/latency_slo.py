"""Moonshot 11 + Phase 1D — Latency SLO panel.

p50/p95 for scripted vs live vs tool_runtime.
Separates timeout-inflated live from completed live so the board is honest.
Alert when live_completed p95 > 10x scripted (or all-live if no completes).
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
# Wall times at/above this are treated as timeout-class for SLO split
TIMEOUT_FLOOR_S = float(os.getenv("ETHER_LATENCY_TIMEOUT_FLOOR_S", "120"))


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


def _is_timeout_row(row: Dict[str, Any], d: float) -> bool:
    reason = str(row.get("reason") or row.get("failure_type") or "").lower()
    note = str(row.get("note") or "").lower()
    hay = reason + " " + note
    if "timeout" in hay or "failed_terminal" in hay:
        return True
    if not bool(row.get("ok")) and d >= TIMEOUT_FLOOR_S:
        return True
    return False


def compute() -> Dict[str, Any]:
    from core.honest_live import collect_scoreboard_rows, classify_row

    rows = collect_scoreboard_rows()
    scripted: List[float] = []
    live_all: List[float] = []
    live_ok: List[float] = []
    live_timeout: List[float] = []
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
            live_all.append(d)
            if _is_timeout_row(r, d):
                live_timeout.append(d)
            elif bool(r.get("ok")):
                live_ok.append(d)
            else:
                # failed but not timeout-class — still count in all, not ok
                pass
        if "tool_runtime" in strat or c.get("toolish"):
            tool_rt.append(d)

    def bucket(vals: List[float]) -> Dict[str, Any]:
        return {
            "n": len(vals),
            "p50": _pct(vals, 50),
            "p95": _pct(vals, 95),
            "max": round(max(vals), 3) if vals else None,
        }

    sb = bucket(scripted)
    lb_all = bucket(live_all)
    lb_ok = bucket(live_ok)
    lb_to = bucket(live_timeout)
    tb = bucket(tool_rt)

    # Primary product ratio: prefer completed live when we have samples
    primary_live = lb_ok if lb_ok["n"] > 0 else lb_all
    ratio = None
    ratio_all = None
    alert = False
    if sb.get("p95") and sb["p95"] > 0:
        if lb_all.get("p95"):
            ratio_all = round(lb_all["p95"] / sb["p95"], 2)
        if primary_live.get("p95"):
            ratio = round(primary_live["p95"] / sb["p95"], 2)
            alert = ratio > ALERT_RATIO
        elif ratio_all is not None:
            ratio = ratio_all
            alert = ratio_all > ALERT_RATIO

    timeout_rate = None
    if live_all:
        timeout_rate = round(len(live_timeout) / len(live_all), 4)

    payload = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "scripted": sb,
        "live": lb_all,
        "live_completed": lb_ok,
        "live_timeout": lb_to,
        "tool_runtime": tb,
        "live_over_scripted_p95": ratio,
        "live_all_over_scripted_p95": ratio_all,
        "live_timeout_rate": timeout_rate,
        "timeout_floor_s": TIMEOUT_FLOOR_S,
        "alert_ratio_threshold": ALERT_RATIO,
        "alert": alert,
        "note": (
            "Primary ratio uses completed live when n>0; live_all includes timeouts. "
            "Alert when primary live p95 > Nx scripted p95."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
