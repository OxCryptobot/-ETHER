"""Moonshot panels for Control Matrix — host-agent artifacts only."""
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
    smoothness = _read("smoothness.json")
    honest_kpi = _read("honest_kpi.json")
    latency = _read("latency_slo.json")
    soft = _read("soft_launch_status.json")
    measure = _read("measure_tick.json")
    micro = _read("microbench.json")
    frozen = (ARTIFACTS / "steady_frozen.json").exists()
    gem = _read("gem_energy.json")
    rates = _read("honest_live_rates.json")
    live_budget = _read("live_budget.json")
    plan_wire = _read("critique_plan_wire.json")
    strangler = _read("pipeline_strangler.json")
    ast_kpi = _read("ast_edit_kpi.json")
    phase1d = _read("phase1d_status.json")
    ctx = _read("context_budget.json")
    tdiag = _read("timeout_diagnosis.json")
    retire = _read("timeout_retirement.json")

    adapter_on = False
    try:
        from core.pipeline_adapter import terminal_adapter_enabled

        adapter_on = terminal_adapter_enabled()
    except Exception:
        adapter_on = False

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

    lat_val = latency.get("live_over_scripted_p95")
    lat_all = latency.get("live_all_over_scripted_p95")
    to_rate = latency.get("live_timeout_rate")
    lat_sub = "completed/scripted p95"
    if to_rate is not None:
        lat_sub = f"to_rate={to_rate} all={lat_all}"

    top_fx = "—"
    if tdiag.get("top_fixtures"):
        top_fx = str(tdiag["top_fixtures"][0].get("fixture") or "—")[:28]

    retire_action = "—"
    acts = retire.get("actions") or []
    if acts:
        retire_action = str(acts[0])[:36]

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
            "value": lat_val,
            "sub": lat_sub,
            "good": not latency.get("alert"),
            "warn": bool(latency.get("alert")),
        },
        {
            "id": "live_timeout",
            "label": "Live timeouts",
            "value": to_rate if to_rate is not None else "—",
            "sub": f"n_to={(latency.get('live_timeout') or {}).get('n')}",
            "good": (to_rate or 0) < 0.25 if isinstance(to_rate, (int, float)) else None,
            "warn": isinstance(to_rate, (int, float)) and 0.25 <= to_rate < 0.5,
        },
        {
            "id": "timeout_diag",
            "label": "Timeout top fixture",
            "value": top_fx,
            "sub": f"rate={tdiag.get('timeout_rate')} n={tdiag.get('timeout_n')}",
            "good": bool(tdiag.get("ok")),
            "warn": not bool(tdiag.get("ok")) if tdiag else None,
        },
        {
            "id": "timeout_retire",
            "label": "Timeout retirement",
            "value": retire_action,
            "sub": f"rate={retire.get('timeout_rate')} target={retire.get('target_rate')}",
            "good": bool(retire.get("ok")),
            "warn": not bool(retire.get("ok")) if retire else None,
        },
        {
            "id": "context",
            "label": "Context budget",
            "value": ctx.get("grade") or ctx.get("status") or "—",
            "sub": f"util={ctx.get('utilization')}",
            "good": (ctx.get("grade") or "") in ("OK", "COMPRESSED"),
            "warn": (ctx.get("grade") or "") in ("WARM", "HOT"),
        },
        {
            "id": "strangler",
            "label": "Pipeline slice",
            "value": strangler.get("status") or "—",
            "sub": f"{strangler.get('extracted_ok')}/{strangler.get('extracted_n')} "
            f"kb={round((strangler.get('pipeline_bytes') or 0)/1024, 1)}",
            "good": strangler.get("status") in ("STRANGLER_ACTIVE", "HEALTHY_SLICE"),
            "warn": strangler.get("over_budget") is True,
        },
        {
            "id": "adapter",
            "label": "Terminal adapter",
            "value": "ON" if adapter_on else "OFF",
            "sub": "ETHER_PIPELINE_TERMINAL",
            "good": not adapter_on,
            "warn": adapter_on,
        },
        {
            "id": "soft_launch",
            "label": "Soft launch",
            "value": soft.get("status")
            or ("blocked" if soft.get("soft_launch_blocked") else "—"),
            "sub": (soft.get("note") or "")[:40],
            "good": bool(soft.get("soft_launch_ready")),
            "warn": soft.get("soft_launch_blocked") is True,
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
            "id": "phase1d",
            "label": "1D status",
            "value": phase1d.get("status") or "—",
            "sub": f"{phase1d.get('checks_ok')}/{phase1d.get('checks_n')}",
            "good": phase1d.get("status") in ("ADVANCING", "PARTIAL"),
        },
        {
            "id": "live_budget",
            "label": "Live budget",
            "value": live_budget.get("max_wall_s") or "—",
            "sub": f"steps={live_budget.get('max_steps')} wall_s",
            "good": isinstance(live_budget.get("max_wall_s"), int)
            and live_budget.get("max_wall_s") <= 120,
            "warn": wheels_on,
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
            "id": "measure_tick",
            "label": "Measure tick",
            "value": measure.get("ok") if measure else "—",
            "sub": f"age={_age_s(measure.get('timestamp') or measure.get('updated'))}s",
            "good": measure.get("ok") is True,
        },
    ]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tiles": tiles,
        "raw": {
            "smoothness": smoothness,
            "honest_kpi": honest_kpi,
            "latency_slo": latency,
            "timeout_diagnosis": tdiag,
            "timeout_retirement": retire,
            "context": ctx,
            "live_budget": live_budget,
            "strangler": strangler,
            "adapter_on": adapter_on,
            "ast_kpi": ast_kpi,
            "soft_launch": soft,
            "measure_tick": measure,
            "plan_wire": plan_wire,
            "frozen": frozen,
            "wheels_on": wheels_on,
            "pending_n": pending_n,
            "live_rates": rates,
            "gem": gem,
            "micro": micro,
        },
        "note": "Host-first + timeout retirement plan tile.",
    }
