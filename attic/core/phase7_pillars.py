"""Phase 7 — Core Identity three-pillar canary.

1. Modular Intelligence (8 gems)
2. Verified Execution (sandbox / score path)
3. Controlled Evolution (dry LoRA + critique wire + lessons)

Does not soft-launch. Does not train.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "phase7_pillars.json"


def check() -> Dict[str, Any]:
    pillars: List[Dict[str, Any]] = []

    # 1 Modular Intelligence
    try:
        from core.gem_energy import GEMS, publish

        g = publish()
        ok = len(GEMS) == 8 and len(g.get("gems") or []) == 8
        pillars.append(
            {
                "id": "modular_intelligence",
                "name": "8 specialized gems",
                "ok": ok,
                "detail": ",".join(GEMS),
            }
        )
    except Exception as e:
        pillars.append(
            {"id": "modular_intelligence", "name": "8 specialized gems", "ok": False, "detail": str(e)[:120]}
        )

    # 2 Verified Execution
    try:
        from core.pipeline_score import clamp_score, terminal_fail_envelope
        from core.pipeline_tool_first import decide_pipeline_tool_first

        d = decide_pipeline_tool_first(
            tool_runtime_enabled=True, tool_runtime_done=False
        )
        env = terminal_fail_envelope(stage="tool_runtime", marker="tool_runtime_failed_terminal")
        ok = d.should_fail and env.get("ok") is False and clamp_score(1.5) == 1.0
        pillars.append(
            {
                "id": "verified_execution",
                "name": "Sandbox score + tool-first terminal",
                "ok": ok,
                "detail": f"fail_marker={d.degrade_marker}",
            }
        )
    except Exception as e:
        pillars.append(
            {
                "id": "verified_execution",
                "name": "Sandbox score + tool-first terminal",
                "ok": False,
                "detail": str(e)[:120],
            }
        )

    # 3 Controlled Evolution
    try:
        from core.lora_dry_tick import dry_tick
        from core.critique_plan_wire import wire_latest
        from core.phase5_lessons import inventory

        dry = dry_tick(force=True)
        wire = wire_latest(limit=5)
        les = inventory()
        ok = (
            dry.get("trained") is False
            and dry.get("dry_run") is True
            and wire.get("training_wheels") is True
            and les.get("ok") is True
        )
        pillars.append(
            {
                "id": "controlled_evolution",
                "name": "Dry LoRA + critique→plan + lessons",
                "ok": ok,
                "detail": f"lora_trained={dry.get('trained')} lessons={les.get('n_lessons')}",
            }
        )
    except Exception as e:
        pillars.append(
            {
                "id": "controlled_evolution",
                "name": "Dry LoRA + critique→plan + lessons",
                "ok": False,
                "detail": str(e)[:120],
            }
        )

    wheels = (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0"
    all_ok = all(p["ok"] for p in pillars) and wheels
    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "phase": "7",
        "pillars": pillars,
        "pillars_ok": sum(1 for p in pillars if p["ok"]),
        "pillars_n": len(pillars),
        "training_wheels": wheels,
        "ok": all_ok,
        "note": "Identity pillars measured. Not a soft-launch certificate.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(check(), indent=2))
