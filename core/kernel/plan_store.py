"""Persist plan DAG for Matrix RO and exe resume."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict
from core.kernel.plan import Node, PlanGraph

def dump(plan: PlanGraph) -> Dict[str, Any]:
    return {
        "goal": plan.goal,
        "nodes": {
            nid: {
                "id": n.id,
                "goal": n.goal,
                "depends_on": list(n.depends_on),
                "status": n.status,
                "confidence": n.confidence,
                "class_": n.class_,
            }
            for nid, n in plan.nodes.items()
        },
    }

def load(row: Dict[str, Any]) -> PlanGraph:
    plan = PlanGraph(goal=str(row.get("goal") or ""))
    for raw in (row.get("nodes") or {}).values():
        plan.add(Node(
            id=str(raw.get("id") or ""),
            goal=str(raw.get("goal") or ""),
            depends_on=list(raw.get("depends_on") or []),
            status=str(raw.get("status") or "open"),
            confidence=float(raw.get("confidence") or 0.5),
            class_=str(raw.get("class_") or "fast"),
        ))
    return plan

def save(plan: PlanGraph, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dump(plan), indent=2) + "\n", encoding="utf-8")
    return path

def replan_low(plan: PlanGraph, node_id: str, threshold: float = 0.4) -> bool:
    node = plan.nodes.get(node_id)
    if node is None or node.confidence >= threshold:
        return False
    node.status = "open"
    plan._refresh()
    return True
