"""Phase 5 — moonshot / research registry.

Inventory of experimental ideas already partially instrumented.
Does not enable experimental flags. Does not lift wheels.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "phase5_moonshots.json"
ART = ROOT / "artifacts"

# id, name, artifact hint, status
MOONSHOTS: List[Dict[str, str]] = [
    {"id": "M11", "name": "Latency SLO panel", "artifact": "latency_slo.json"},
    {"id": "M12", "name": "Honest-live sparkline", "artifact": "honest_sparkline.json"},
    {"id": "M13", "name": "FAST-first hard scheduler", "artifact": ""},
    {"id": "M14", "name": "Context budget meter", "artifact": "context_budget.json"},
    {"id": "M15", "name": "Speculative scripted shadow", "artifact": "shadow_tags.json"},
    {"id": "M16", "name": "Queue depth governor", "artifact": ""},
    {"id": "M17", "name": "Model router latency class", "artifact": "model_router.json"},
    {"id": "M18", "name": "GEM energy strip", "artifact": "gem_energy.json"},
    {"id": "M19", "name": "Train-wheels fuse", "artifact": ""},
    {"id": "M20", "name": "Scoreboard auto-rollup", "artifact": "scoreboard_latest.json"},
    {"id": "M21", "name": "Critique → PlanState wire", "artifact": "critique_plan_wire.json"},
    {"id": "M22", "name": "AST-edit success rate tile", "artifact": "ast_edit_kpi.json"},
    {"id": "M23", "name": "Zero-click recovery", "artifact": ""},
    {"id": "M24", "name": "Hot-path microbench", "artifact": "microbench.json"},
    {"id": "M25", "name": "Control Matrix smoothness", "artifact": "smoothness.json"},
]


def registry() -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    present = 0
    for m in MOONSHOTS:
        path = ART / m["artifact"] if m["artifact"] else None
        exists = bool(path and path.exists())
        if exists:
            present += 1
        rows.append(
            {
                "id": m["id"],
                "name": m["name"],
                "artifact": m["artifact"] or None,
                "instrumented": exists or not m["artifact"],
                "artifact_present": exists,
            }
        )

    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "phase": "5",
        "n": len(rows),
        "artifact_present_n": present,
        "moonshots": rows,
        "experimental_flags_on": False,
        "ok": len(rows) >= 15,
        "note": "Research registry only. Enabling experiments requires explicit flags.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(registry(), indent=2))
