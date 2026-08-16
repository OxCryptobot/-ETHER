"""Phase 7 — living autonomous agent checklist.

Maps ambition (self-learn / self-evolve) to measured surfaces.
Does not claim the agent is fully autonomous.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "phase7_living_checklist.json"


def checklist() -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []

    def add(iid: str, name: str, ok: bool, status: str, detail: str = "") -> None:
        items.append(
            {
                "id": iid,
                "name": name,
                "ok": bool(ok),
                "status": status,
                "detail": detail[:140],
            }
        )

    # Durable state
    try:
        from core.agent_state import AgentState

        s = AgentState(thread_id="p7_living")
        s.objective = "checklist"
        s.save()
        add("durable_state", "AgentState durable", AgentState.load("p7_living") is not None, "READY")
    except Exception as e:
        add("durable_state", "AgentState durable", False, "GAP", str(e))

    # Verified execution path
    try:
        from core.pipeline_terminal_canary import run_matrix

        t = run_matrix()
        add("verified_path", "Terminal pure canary", bool(t.get("ok")), "READY" if t.get("ok") else "GAP")
    except Exception as e:
        add("verified_path", "Terminal pure canary", False, "GAP", str(e))

    # Self-critique loop
    try:
        from core.critique_plan_wire import wire_latest

        w = wire_latest(limit=5)
        add(
            "self_critique",
            "Critique → Plan wire",
            True,
            "READY",
            f"n={w.get('n_critiques')} replan={w.get('n_replanned')}",
        )
    except Exception as e:
        add("self_critique", "Critique → Plan wire", False, "GAP", str(e))

    # Day-by-day memory
    try:
        from core.phase5_lessons import inventory

        les = inventory()
        add(
            "day_memory",
            "Lessons journal",
            bool(les.get("ok")),
            "READY",
            f"n={les.get('n_lessons')}",
        )
    except Exception as e:
        add("day_memory", "Lessons journal", False, "GAP", str(e))

    # Tool self-extension (quarantine path)
    try:
        from core.phase4_toolkit import inventory

        inv = inventory()
        add(
            "tool_extension",
            "Toolkit quarantine path",
            bool(inv.get("ok")) and inv.get("auto_promote") is False,
            "READY",
            f"q={inv.get('quarantine_n')}",
        )
    except Exception as e:
        add("tool_extension", "Toolkit quarantine path", False, "GAP", str(e))

    # Honest measurement (not green rates — surface exists)
    try:
        from core.phase1_gate import compute as gate

        g = gate()
        add(
            "honest_gate",
            "Phase1 metrics gate surface",
            "metrics_go" in g,
            "BLOCKED" if not g.get("metrics_go") else "READY",
            f"metrics_go={g.get('metrics_go')} status={g.get('status')}",
        )
    except Exception as e:
        add("honest_gate", "Phase1 metrics gate surface", False, "GAP", str(e))

    # Soft launch must stay blocked on checklist
    add(
        "soft_launch",
        "Soft launch",
        True,
        "LOCKED",
        "Intentionally locked until eligible honest LIVE rates",
    )

    ready = sum(1 for i in items if i["status"] == "READY")
    locked = sum(1 for i in items if i["status"] == "LOCKED")
    gaps = sum(1 for i in items if i["status"] == "GAP")
    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "phase": "7",
        "items": items,
        "ready_n": ready,
        "locked_n": locked,
        "gap_n": gaps,
        "autonomous_claim": False,
        "ok": gaps == 0,
        "note": (
            "Checklist for living-agent ambition. autonomous_claim stays false "
            "until metrics_go + human soft-launch."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(checklist(), indent=2))
