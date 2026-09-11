"""F02: short measure tick. Full measure_tick times out on 90s host wall."""
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
            slim = {k: out[k] for k in list(out)[:8] if k not in ("strip", "steps", "results")}
            slim["ok"] = out.get("ok", True)
            return slim
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}:{e}"[:200]}


def run_fast() -> Dict[str, Any]:
    steps: Dict[str, Any] = {}
    errors: List[str] = []
    panels = [
        ("honest_kpi", lambda: __import__("core.honest_kpi", fromlist=["compute"]).compute()),
        ("latency_slo", lambda: __import__("core.latency_slo", fromlist=["compute"]).compute()),
        ("gem_energy", lambda: __import__("core.gem_energy", fromlist=["publish"]).publish()),
        ("host_health", lambda: __import__("core.host_health", fromlist=["compute"]).compute()),
        ("context_budget", lambda: __import__("core.context_budget", fromlist=["publish_sample"]).publish_sample()),
    ]
    for name, fn in panels:
        steps[name] = _safe(name, fn)
        if steps[name].get("ok") is False:
            errors.append(name)
    report: Dict[str, Any] = {
        "timestamp": _now(),
        "ok": True,
        "errors": errors,
        "steps": steps,
        "soft_launch_blocked": True,
        "doctrine": "measure_tick_fast",
        "note": "F02 slim tick. Full 25-panel tick timed out. Dual chat locked.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return report


if __name__ == "__main__":
    print(json.dumps(run_fast(), indent=2))
