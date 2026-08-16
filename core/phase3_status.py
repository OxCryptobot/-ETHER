"""Phase 3 status — controlled evolution measurement package.

MEASURE_COMPLETE when AgentState, LoRA dry, critique wire, gems, tool-first,
and snapshot canaries pass under wheels ON.

Real train + soft launch remain LOCKED.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "phase3_status.json"


def compute() -> Dict[str, Any]:
    packages: List[Dict[str, Any]] = []

    def pkg(pid: str, name: str, ok: bool, detail: str = "") -> None:
        packages.append(
            {"id": pid, "name": name, "ok": bool(ok), "detail": detail[:160]}
        )

    try:
        from core.phase3_canaries import run_matrix

        c = run_matrix()
        pkg(
            "3-canaries",
            "Phase 3 canary matrix",
            bool(c.get("ok")),
            f"{c.get('passed')}/{c.get('n')}",
        )
        for case in c.get("cases") or []:
            packages.append(
                {
                    "id": f"3-{case.get('name')}",
                    "name": str(case.get("name")),
                    "ok": bool(case.get("pass")),
                    "detail": str(case.get("detail") or "")[:120],
                }
            )
    except Exception as e:
        pkg("3-canaries", "Phase 3 canary matrix", False, str(e))

    try:
        from core.phase3_snapshot import build_snapshot

        s = build_snapshot()
        pkg(
            "3-snapshot",
            "Soft-launch measurement snapshot",
            bool(s.get("ok")) and s.get("soft_launch_blocked") is True,
            f"live_honest={s.get('honest_live', {}).get('live_honest_rate')}",
        )
    except Exception as e:
        pkg("3-snapshot", "Soft-launch measurement snapshot", False, str(e))

    try:
        from core.phase2_status import compute as p2

        p2s = p2()
        pkg(
            "3-phase2-arch",
            "Phase 2 architecture prerequisite",
            bool(p2s.get("architecture_complete")) or p2s.get("status") == "ARCH_COMPLETE",
            str(p2s.get("status")),
        )
    except Exception as e:
        pkg("3-phase2-arch", "Phase 2 architecture prerequisite", False, str(e))

    wheels = (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0"
    pkg("3-wheels", "Training wheels ON", wheels, f"wheels={wheels}")

    measure_ids = {
        "3-canaries",
        "3-snapshot",
        "3-agent_state_roundtrip",
        "3-lora_dry_only",
        "3-critique_plan_wire",
        "3-gems_eight",
        "3-tool_first_gate",
        "3-phase3_snapshot",
        "3-flags_default_safe",
        "3-wheels",
    }
    measure_pkgs = [p for p in packages if p["id"] in measure_ids]
    # If expanded case ids present use those; else canaries+snapshot+wheels
    if len(measure_pkgs) < 3:
        measure_pkgs = [p for p in packages if p["id"] in ("3-canaries", "3-snapshot", "3-wheels")]
    measure_complete = all(p["ok"] for p in measure_pkgs) and wheels

    locked = [
        {
            "id": "3B-lora-train",
            "name": "Real LoRA train / promote",
            "status": "LOCKED",
            "reason": "needs ETHER_LORA_TRAIN=1 + ETHER_LORA_PROMOTE=1 + preference health",
        },
        {
            "id": "3C-soft-launch",
            "name": "Soft launch",
            "status": "LOCKED",
            "reason": "metrics_go + human ETHER_SOFT_LAUNCH=1 + wheels policy",
        },
        {
            "id": "3D-loop-runner-live",
            "name": "ETHER_LOOP_RUNNER live path",
            "status": "LOCKED",
            "reason": "flag default OFF until measured suite green",
        },
        {
            "id": "3E-symbol-index-live",
            "name": "ETHER_SYMBOL_INDEX in Pipeline",
            "status": "LOCKED",
            "reason": "flag default OFF; snapshot-only until gate",
        },
    ]

    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "phase": "3",
        "name": "Controlled evolution measurement",
        "measure_complete": measure_complete,
        "status": "MEASURE_COMPLETE" if measure_complete else "MEASURE_IN_PROGRESS",
        "packages": packages,
        "packages_ok": sum(1 for p in packages if p["ok"]),
        "packages_n": len(packages),
        "locked": locked,
        "training_wheels": wheels,
        "soft_launch_blocked": True,
        "lora_train_blocked": True,
        "note": (
            "Phase 3 complete = durable state + dry LoRA + critique→plan + 8 gems "
            "+ tool-first gate under wheels. Real train and soft launch stay LOCKED."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
