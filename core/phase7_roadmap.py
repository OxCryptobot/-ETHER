"""Phase 7 — full roadmap rollup and remaining real work."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "phase7_roadmap.json"


def rollup() -> Dict[str, Any]:
    phases: List[Dict[str, Any]] = []

    def add(num: str, name: str, status: str, detail: str = "") -> None:
        phases.append({"phase": num, "name": name, "status": status, "detail": detail[:140]})

    try:
        from core.phase1_gate import compute as g1

        g = g1()
        add("1", "Critical metrics gate", str(g.get("status")), f"metrics_go={g.get('metrics_go')}")
    except Exception as e:
        add("1", "Critical metrics gate", "UNKNOWN", str(e))

    for mod, num, name, key in (
        ("core.phase2_status", "2", "Architecture", "architecture_complete"),
        ("core.phase3_status", "3", "Evolution measure", "measure_complete"),
        ("core.phase4_status", "4", "Capability scaffolds", "scaffold_complete"),
        ("core.phase5_status", "5", "Experiment registry", "experiment_complete"),
        ("core.phase6_status", "6", "Operator OS", "operator_complete"),
    ):
        try:
            m = __import__(mod, fromlist=["compute"])
            out = m.compute()
            complete = bool(out.get(key))
            add(num, name, str(out.get("status")), f"{key}={complete}")
        except Exception as e:
            add(num, name, "UNKNOWN", str(e)[:80])

    add("7", "North star package", "IN_PROGRESS", "this module")

    remaining = [
        {
            "id": "R1",
            "work": "Raise eligible LIVE honest rate toward 0.99",
            "blocks": "metrics_go / soft launch",
        },
        {
            "id": "R2",
            "work": "Cut eligible timeout rate < 0.25 with denylist + retirement",
            "blocks": "metrics_go",
        },
        {
            "id": "R3",
            "work": "Dual-run shadow then optional ETHER_PIPELINE_TERMINAL",
            "blocks": "Pipeline.run cutover",
        },
        {
            "id": "R4",
            "work": "Human soft-launch flags after metrics_go",
            "blocks": "product soft launch",
        },
    ]

    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "phase": "7",
        "phases": phases,
        "remaining_real_work": remaining,
        "soft_launch_blocked": True,
        "training_wheels": (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0",
        "ok": True,
        "note": "Roadmap truth. Package green ≠ product green.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(rollup(), indent=2))
