"""Phase 4 status — advanced capability scaffolds.

SCAFFOLD_COMPLETE when toolkit inventory, MCP schema, and plan-only swarm pass.
Live MCP server, auto-promote, and multi-agent GPU remain LOCKED.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "phase4_status.json"


def compute() -> Dict[str, Any]:
    packages: List[Dict[str, Any]] = []

    def pkg(pid: str, name: str, ok: bool, detail: str = "") -> None:
        packages.append(
            {"id": pid, "name": name, "ok": bool(ok), "detail": detail[:160]}
        )

    try:
        from core.phase4_toolkit import inventory

        t = inventory()
        pkg(
            "4-toolkit",
            "Toolkit inventory + auto-promote OFF",
            bool(t.get("ok")),
            f"q={t.get('quarantine_n')} p={t.get('persistent_n')} auto={t.get('auto_promote')}",
        )
    except Exception as e:
        pkg("4-toolkit", "Toolkit inventory", False, str(e))

    try:
        from core.phase4_mcp_schema import build_registry

        m = build_registry()
        pkg(
            "4-mcp-schema",
            "MCP schema registry (offline)",
            bool(m.get("ok")) and m.get("server_live") is False,
            f"tools={m.get('n_tools')} live={m.get('server_live')}",
        )
    except Exception as e:
        pkg("4-mcp-schema", "MCP schema registry", False, str(e))

    try:
        from core.phase4_swarm_plan import plan

        s = plan("implement fix and pytest verify", max_agents=4)
        pkg(
            "4-swarm-plan",
            "Plan-only swarm",
            bool(s.get("ok")) and s.get("spawned") is False,
            f"agents={s.get('n_agents')} spawned={s.get('spawned')}",
        )
    except Exception as e:
        pkg("4-swarm-plan", "Plan-only swarm", False, str(e))

    try:
        from core.phase3_status import compute as p3

        p3s = p3()
        pkg(
            "4-phase3-prereq",
            "Phase 3 measure prerequisite",
            bool(p3s.get("measure_complete")) or p3s.get("status") == "MEASURE_COMPLETE",
            str(p3s.get("status")),
        )
    except Exception as e:
        pkg("4-phase3-prereq", "Phase 3 measure prerequisite", False, str(e))

    wheels = (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0"
    pkg("4-wheels", "Training wheels ON", wheels, f"wheels={wheels}")

    core_ids = {"4-toolkit", "4-mcp-schema", "4-swarm-plan", "4-wheels"}
    core = [p for p in packages if p["id"] in core_ids]
    scaffold_complete = all(p["ok"] for p in core)

    locked = [
        {
            "id": "4B-mcp-server",
            "name": "Live MCP HTTP server",
            "status": "LOCKED",
            "reason": "schema-only until metrics_go + explicit flag",
        },
        {
            "id": "4C-auto-promote",
            "name": "ETHER_AUTO_PROMOTE tool promotion",
            "status": "LOCKED",
            "reason": "quarantine + audit gates + human flag",
        },
        {
            "id": "4D-swarm-live",
            "name": "Multi-agent GPU swarm execution",
            "status": "LOCKED",
            "reason": "plan-only; host is ≤4B single-lane",
        },
        {
            "id": "4E-llm-fabricate",
            "name": "LLM full tool fabricate (non-stub)",
            "status": "LOCKED",
            "reason": "needs ollama + safety audit; stub path only in Phase 4",
        },
    ]

    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "phase": "4",
        "name": "Advanced capability scaffolds",
        "scaffold_complete": scaffold_complete,
        "status": "SCAFFOLD_COMPLETE" if scaffold_complete else "SCAFFOLD_IN_PROGRESS",
        "packages": packages,
        "packages_ok": sum(1 for p in packages if p["ok"]),
        "packages_n": len(packages),
        "locked": locked,
        "training_wheels": wheels,
        "soft_launch_blocked": True,
        "note": (
            "Phase 4 complete = toolkit safety inventory + MCP schema + plan-only swarm. "
            "No live MCP, no auto-promote, no multi-agent GPU."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
