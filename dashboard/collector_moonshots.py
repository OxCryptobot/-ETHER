"""Moonshot panels for Control Matrix — host-agent artifacts only.

No flywheel / guardian / legacy batch. Reads measure_tick outputs under artifacts/.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"


def _read(name: str) -> Dict[str, Any]:
    p = ARTIFACTS / name
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"error": str(e)[:120]}


def _age_s(iso: Optional[str]) -> Optional[float]:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return round((datetime.now(timezone.utc) - dt).total_seconds(), 1)
    except Exception:
        return None


def collect_moonshots() -> Dict[str, Any]:
    """Fifteen host-first panels for the unified Control Matrix."""
    smoothness = _read("smoothness.json")
    honest_kpi = _read("honest_kpi.json")
    latency = _read("latency_slo.json")
    spark = _read("honest_sparkline.json")
    ctx = _read("context_budget.json")
    rollup = _read("scoreboard_latest.json")
    soft = _read("soft_launch_status.json")
    measure = _read("measure_tick.json")
    micro = _read("microbench.json")
    frozen = (ARTIFACTS / "steady_frozen.json").exists()
    gem = _read("gem_energy.json")
    rates = _read("honest_live_rates.json")
    phase3 = _read("phase3_snapshot.json")

    # Queue governor signal from pending count
    pending_n = 0
    pending_dir = ARTIFACTS / "jobs" / "pending"
    if pending_dir.exists():
        pending_n = sum(1 for p in pending_dir.glob("*.json") if p.name != ".gitkeep")

    wheels_on = True
    try:
        import os

        wheels_on = (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0"
    except Exception:
        pass

    tiles: List[Dict[str, Any]] = [
        {
            "id": "smoothness",
            "label": "Smoothness",
            "value": smoothness.get("score"),
            "sub": smoothness.get("grade") or "—",
            "good": (smoothness.get("score") or 0) >= 70,
            "warn": 50 <= (smoothness.get("score") or 0) < 70,
        },
        {
            "id": "honest_kpi",
            "label": "Honest KPI",
            "value": honest_kpi.get("primary_kpi") or "—",
            "sub": f"rate={honest_kpi.get('honest_rate')}",
            "good": (honest_kpi.get("honest_rate") or 0) >= 0.5,
            "warn": 0 < (honest_kpi.get("honest_rate") or 0) < 0.5,
        },
        {
            "id": "latency_slo",
            "label": "Latency SLO",
            "value": latency.get("live_over_scripted_p95"),
            "sub": "live/scripted p95",
            "good": not latency.get("alert"),
            "warn": bool(latency.get("alert")),
        },
        {
            "id": "sparkline",
            "label": "Honest spark",
            "value": (spark.get("summary") or spark.get("last") or spark.get("n") or "—"),
            "sub": "last runs",
            "good": True if spark else None,
        },
        {
            "id": "queue_gov",
            "label": "Queue depth",
            "value": pending_n,
            "sub": "governor cap 8",
            "good": pending_n <= 6,
            "warn": 6 < pending_n <= 8,
        },
        {
            "id": "context",
            "label": "Context budget",
            "value": ctx.get("ratio") or ctx.get("tokens_in") or ctx.get("status") or "—",
            "sub": ctx.get("note") or "tokens/max",
            "good": True if ctx and not ctx.get("error") else None,
        },
        {
            "id": "soft_launch",
            "label": "Soft launch",
            "value": soft.get("status") or soft.get("blocked") or ("ready" if soft.get("ok") else "—"),
            "sub": (soft.get("reason") or soft.get("note") or "")[:40],
            "good": bool(soft.get("ok")),
            "warn": soft.get("blocked") is True,
        },
        {
            "id": "train_wheels",
            "label": "Train wheels",
            "value": "ON" if wheels_on else "OFF",
            "sub": "LIVE fuse",
            "good": not wheels_on,
            "warn": wheels_on,
        },
        {
            "id": "rollup",
            "label": "Scoreboard",
            "value": rollup.get("honest_rate") or rollup.get("summary") or rollup.get("n") or "—",
            "sub": "latest rollup",
            "good": True if rollup and not rollup.get("error") else None,
        },
        {
            "id": "microbench",
            "label": "Microbench",
            "value": micro.get("ok") if micro else ("FROZEN" if frozen else "—"),
            "sub": "hot-path / freeze",
            "good": micro.get("ok") is True and not frozen,
            "warn": frozen or micro.get("ok") is False,
        },
        {
            "id": "gem_energy",
            "label": "GEM energy",
            "value": gem.get("last_gem") or gem.get("gem") or "—",
            "sub": gem.get("last_job") or "modular intel",
            "good": True if gem else None,
        },
        {
            "id": "measure_tick",
            "label": "Measure tick",
            "value": measure.get("ok") if measure else "—",
            "sub": f"age={_age_s(measure.get('updated') or measure.get('ts'))}s",
            "good": measure.get("ok") is True,
        },
        {
            "id": "honest_rates",
            "label": "Live rates",
            "value": rates.get("honest_rate") or rates.get("primary") or "—",
            "sub": "honest_live_rates",
            "good": (rates.get("honest_rate") or 0) >= 0.2 if isinstance(rates.get("honest_rate"), (int, float)) else None,
        },
        {
            "id": "phase3",
            "label": "Phase3 snap",
            "value": phase3.get("status") or phase3.get("ok") or "—",
            "sub": "snapshot",
            "good": phase3.get("ok") is True,
        },
        {
            "id": "model_lane",
            "label": "Model lane",
            "value": "qwen4b FAST",
            "sub": "router: FAST vs LIVE",
            "good": True,
        },
    ]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tiles": tiles,
        "raw": {
            "smoothness": smoothness,
            "honest_kpi": honest_kpi,
            "latency_slo": latency,
            "soft_launch": soft,
            "measure_tick": measure,
            "microbench": micro,
            "frozen": frozen,
            "wheels_on": wheels_on,
            "pending_n": pending_n,
        },
        "note": "Host-first moonshot panels only. No legacy flywheel/guardian.",
    }
