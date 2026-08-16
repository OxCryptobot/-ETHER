"""Measure tick — rates + all moonshot observability panels."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "measure_tick.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe(name: str, fn) -> Dict[str, Any]:
    try:
        out = fn()
        if isinstance(out, dict):
            slim = {
                k: out[k]
                for k in list(out)[:12]
                if k not in (
                    "results_tail",
                    "points",
                    "tags",
                    "strip",
                    "events_tail",
                    "checks",
                    "imports",
                    "steps",
                    "top",
                    "results",
                    "samples",
                )
            }
            slim["ok"] = out.get("ok", True)
            return slim
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}:{e}"[:200]}


def run() -> Dict[str, Any]:
    steps: Dict[str, Any] = {}
    errors: List[str] = []

    try:
        from core.honest_live import publish

        rates = publish()
        steps["honest_live"] = {
            "ok": True,
            "status": rates.get("status"),
            "live_n": rates.get("live_n"),
            "live_honest_rate": rates.get("live_honest_rate"),
            "soft_launch_blocked": rates.get("soft_launch_blocked"),
        }
    except Exception as e:
        errors.append(f"honest_live:{e}")
        steps["honest_live"] = {"ok": False, "error": str(e)[:200]}

    panels = [
        ("honest_kpi", lambda: __import__("core.honest_kpi", fromlist=["compute"]).compute()),
        ("latency_slo", lambda: __import__("core.latency_slo", fromlist=["compute"]).compute()),
        ("live_budget", lambda: __import__("core.live_budget", fromlist=["publish"]).publish()),
        (
            "critique_plan_wire",
            lambda: __import__("core.critique_plan_wire", fromlist=["wire_latest"]).wire_latest(),
        ),
        ("honest_sparkline", lambda: __import__("core.honest_sparkline", fromlist=["compute"]).compute()),
        ("context_budget", lambda: __import__("core.context_budget", fromlist=["publish_sample"]).publish_sample()),
        ("scoreboard_rollup", lambda: __import__("core.scoreboard_rollup", fromlist=["rollup"]).rollup()),
        ("shadow_tag", lambda: __import__("core.shadow_tag", fromlist=["compute"]).compute()),
        ("gem_energy", lambda: __import__("core.gem_energy", fromlist=["publish"]).publish()),
        ("ast_edit_kpi", lambda: __import__("core.ast_edit_kpi", fromlist=["compute"]).compute()),
        ("smoothness", lambda: __import__("core.smoothness", fromlist=["compute"]).compute()),
        ("model_router", lambda: __import__("core.model_router", fromlist=["status"]).status()),
        ("phase1d_status", lambda: __import__("core.phase1d_status", fromlist=["compute"]).compute()),
        (
            "pipeline_strangler",
            lambda: __import__("core.pipeline_strangler", fromlist=["compute"]).compute(),
        ),
        (
            "symbol_index",
            lambda: __import__("core.symbol_index_pub", fromlist=["publish"]).publish(),
        ),
        (
            "strangler_style",
            lambda: __import__("core.strangler_style_gate", fromlist=["check"]).check(),
        ),
    ]
    for name, fn in panels:
        steps[name] = _safe(name, fn)
        if steps[name].get("ok") is False:
            errors.append(name)

    try:
        from core.phase3_snapshot import build_snapshot

        snap = build_snapshot()
        steps["phase3_snapshot"] = {"ok": bool(snap.get("ok")), "path": snap.get("path")}
    except Exception as e:
        steps["phase3_snapshot"] = {"ok": False, "error": str(e)[:160]}

    try:
        from core.soft_launch import evaluate

        gate = evaluate()
        steps["soft_launch"] = {
            "ok": True,
            "soft_launch_ready": gate.get("soft_launch_ready"),
            "blocked_reasons": gate.get("blocked_reasons"),
        }
    except Exception as e:
        steps["soft_launch"] = {"ok": False, "error": str(e)[:160]}

    try:
        from core.queue_governor import status_snapshot

        steps["governor"] = status_snapshot()
    except Exception as e:
        steps["governor"] = {"error": str(e)[:120]}

    try:
        from scripts.write_whats_next import main as wn_main

        wn_main()
        steps["whats_next"] = {"ok": True}
    except Exception as e:
        steps["whats_next"] = {"ok": False, "error": str(e)[:120]}

    report: Dict[str, Any] = {
        "timestamp": _now(),
        "ok": len(errors) == 0,
        "errors": errors,
        "steps": steps,
        "soft_launch_blocked": True,
        "doctrine": "moonshot_observability_tick",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return report


if __name__ == "__main__":
    import sys

    print(json.dumps(run(), indent=2))
    sys.exit(0)
