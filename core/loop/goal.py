"""Goal plane. Living gate is MET. Leftover is hardware + more unaided hours."""
from __future__ import annotations

from typing import Any, Dict, Tuple

NORTH_STAR = "Local-first super-agent: 8 gems, pytest as judge, one 4B chair, LIVE scales up."
PILLARS: Tuple[str, ...] = ("modular_intelligence", "verified_execution", "controlled_evolution")
LIVING_GATE = {
    "merge": 3,
    "ledger": 3,
    "need": 3,
    "met": True,
    "policy": "model",
    "wheels": "ON",
}
LEFTOVER = (
    "lora_train_12gb",
    "split_pipeline_godfile",
    "more_unaided_fixtures",
    "operator_outsource_key",
)


def current() -> Dict[str, Any]:
    return {
        "north_star": NORTH_STAR,
        "pillars": list(PILLARS),
        "living_gate": dict(LIVING_GATE),
        "leftover": list(LEFTOVER),
        "max_live_agents": 1,
        "swarm": False,
        "note": "Gate met. FAST stays local 4B. LIVE can outsource or local-large.",
    }


def classify_objective(text: str) -> Dict[str, Any]:
    q = (text or "").lower()
    if any(k in q for k in ("fix", "bug", "ledger", "merge", "pytest", "unaided")):
        kind = "fix_dag"
    elif any(k in q for k in ("lora", "train", "finetune")):
        kind = "moonshot_off_box"
    elif any(k in q for k in ("status", "goal", "phase", "roadmap")):
        kind = "goal"
    else:
        kind = "general"
    return {"kind": kind, "text": (text or "")[:200], "uses_fix_dag": kind == "fix_dag"}
