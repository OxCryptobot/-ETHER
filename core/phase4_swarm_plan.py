"""Phase 4 — plan-only agent swarm decomposition.

Assigns gem roles to subtasks. Does not spawn processes or call GPU.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "phase4_swarm_plan.json"

ROLE_MAP = [
    ("clear-quartz", "verify", ["test", "pytest", "sandbox", "verify"]),
    ("rose-quartz", "implement", ["implement", "code", "fix", "write"]),
    ("citrine", "style", ["style", "pep8", "lint", "format"]),
    ("selenite", "retrieve", ["context", "rag", "search", "index"]),
    ("amethyst", "memory", ["memory", "prefer", "history"]),
    ("black-tourmaline", "security", ["security", "audit", "guard"]),
    ("labradorite", "critique", ["critique", "fail", "replan", "root"]),
    ("grandidierite", "evolve", ["evolve", "lora", "improve"]),
]


def plan(objective: str, max_agents: int = 4) -> Dict[str, Any]:
    obj = (objective or "").lower()
    max_agents = max(1, min(8, int(max_agents or 4)))
    agents: List[Dict[str, Any]] = []
    for gem, role, keys in ROLE_MAP:
        if any(k in obj for k in keys) or not agents:
            agents.append(
                {
                    "gem": gem,
                    "role": role,
                    "task": f"{role}: {objective[:120]}",
                    "live": False,
                }
            )
        if len(agents) >= max_agents:
            break
    # Always include labradorite on non-trivial plans
    if len(agents) >= 2 and not any(a["gem"] == "labradorite" for a in agents):
        agents[-1] = {
            "gem": "labradorite",
            "role": "critique",
            "task": f"critique plan for: {objective[:100]}",
            "live": False,
        }

    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "phase": "4",
        "objective": objective[:300],
        "max_agents": max_agents,
        "agents": agents,
        "n_agents": len(agents),
        "spawned": False,
        "gpu": False,
        "ok": len(agents) >= 1 and all(a.get("live") is False for a in agents),
        "note": "Plan only. No process spawn. No multi-model calls.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    import sys

    obj = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "implement and test feature"
    print(json.dumps(plan(obj), indent=2))
