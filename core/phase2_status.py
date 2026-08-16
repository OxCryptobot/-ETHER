"""Phase 2 architecture status.

ARCH_COMPLETE when pure strangler canaries pass under wheels ON / adapter OFF.
LIVE_UNLOCK (metrics_go) remains separate — soft launch still blocked.

Does not lift wheels. Does not enable ETHER_PIPELINE_TERMINAL.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "phase2_status.json"


def compute() -> Dict[str, Any]:
    packages: List[Dict[str, Any]] = []

    def pkg(pid: str, name: str, ok: bool, detail: str = "") -> None:
        packages.append(
            {"id": pid, "name": name, "ok": bool(ok), "detail": detail[:160]}
        )

    # 2A terminal
    try:
        from core.pipeline_terminal_canary import run_matrix

        t = run_matrix()
        pkg("2A-terminal", "Terminal decision canary", bool(t.get("ok")), f"{t.get('passed')}/{t.get('n')}")
    except Exception as e:
        pkg("2A-terminal", "Terminal decision canary", False, str(e))

    # 2A score
    try:
        from core.pipeline_score_canary import run_matrix as sm

        s = sm()
        pkg("2A-score", "Score/envelope canary", bool(s.get("ok")), f"{s.get('passed')}/{s.get('n')}")
    except Exception as e:
        pkg("2A-score", "Score/envelope canary", False, str(e))

    # 2A slices
    try:
        from core.pipeline_slices_canary import run_matrix as sl

        z = sl()
        pkg("2A-slices", "Prep/context/oracle/tool_first", bool(z.get("ok")), f"{z.get('passed')}/{z.get('n')}")
    except Exception as e:
        pkg("2A-slices", "Prep/context/oracle/tool_first", False, str(e))

    # Strangler inventory
    try:
        from core.pipeline_strangler import compute as st

        inv = st()
        ok = inv.get("extracted_ok") == inv.get("extracted_n") and inv.get(
            "adapter_default_off"
        )
        pkg(
            "2A-strangler",
            "Strangler inventory",
            bool(ok),
            f"{inv.get('extracted_ok')}/{inv.get('extracted_n')} status={inv.get('status')}",
        )
    except Exception as e:
        pkg("2A-strangler", "Strangler inventory", False, str(e))

    # Adapter OFF doctrine
    try:
        from core.pipeline_adapter import terminal_adapter_enabled

        pkg(
            "2A-adapter-off",
            "Adapter default OFF",
            terminal_adapter_enabled() is False,
            f"enabled={terminal_adapter_enabled()}",
        )
    except Exception as e:
        pkg("2A-adapter-off", "Adapter default OFF", False, str(e))

    # Gate
    metrics_go = False
    arch_go = False
    try:
        from core.phase1_gate import compute as gate

        g = gate()
        metrics_go = bool(g.get("metrics_go"))
        arch_go = bool(g.get("architecture_go"))
        pkg(
            "2-gate",
            "Architecture GO / metrics GO",
            arch_go,
            f"arch={arch_go} metrics={metrics_go} status={g.get('status')}",
        )
    except Exception as e:
        pkg("2-gate", "Architecture GO / metrics GO", False, str(e))

    wheels = (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0"
    pkg("2-wheels", "Training wheels ON", wheels, f"wheels={wheels}")

    arch_pkgs = [p for p in packages if p["id"].startswith("2A-") or p["id"] == "2-gate"]
    arch_complete = all(p["ok"] for p in arch_pkgs) and wheels

    # Locked until metrics_go
    locked = [
        {
            "id": "2B-live-wire",
            "name": "Enable ETHER_PIPELINE_TERMINAL on host",
            "status": "LOCKED",
            "reason": "requires metrics_go + human flag",
        },
        {
            "id": "2C-soft-launch",
            "name": "Soft launch / wheels off",
            "status": "LOCKED",
            "reason": "eligible honest rate + human ETHER_SOFT_LAUNCH",
        },
        {
            "id": "2D-pipeline-run-cutover",
            "name": "Pipeline.run body cutover",
            "status": "LOCKED",
            "reason": "strangler canaries green + dual-run shadow under metrics_go",
        },
    ]

    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "phase": "2",
        "architecture_complete": arch_complete,
        "status": "ARCH_COMPLETE" if arch_complete else "ARCH_IN_PROGRESS",
        "packages": packages,
        "packages_ok": sum(1 for p in packages if p["ok"]),
        "packages_n": len(packages),
        "locked_until_metrics_go": locked,
        "architecture_go": arch_go,
        "metrics_go": metrics_go,
        "training_wheels": wheels,
        "soft_launch_blocked": True,
        "note": (
            "Phase 2 architecture = pure strangler canaries under wheels ON. "
            "LIVE wire / soft launch / Pipeline.run cutover stay LOCKED until metrics_go."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
