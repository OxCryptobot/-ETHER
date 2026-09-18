"""Goal → DAG. One live hypothesis node at a time."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional

@dataclass
class Node:
    id: str
    goal: str
    depends_on: List[str] = field(default_factory=list)
    status: str = "open"
    confidence: float = 0.5
    class_: str = "fast"

@dataclass
class PlanGraph:
    goal: str
    nodes: Dict[str, Node] = field(default_factory=dict)

    def add(self, node: Node) -> None:
        self.nodes[node.id] = node
        self._refresh()

    def _refresh(self) -> None:
        for node in self.nodes.values():
            if node.status in {"pass", "fail", "live"}:
                continue
            deps = [self.nodes[d] for d in node.depends_on if d in self.nodes]
            if any(d.status == "fail" for d in deps):
                node.status = "blocked"
            elif all(d.status == "pass" for d in deps):
                node.status = "ready"
            else:
                node.status = "open"

    def next_live(self) -> Optional[Node]:
        self._refresh()
        live = [n for n in self.nodes.values() if n.status == "live"]
        if live:
            return live[0]
        ready = [n for n in self.nodes.values() if n.status == "ready"]
        ready.sort(key=lambda n: (0 if n.class_ == "fast" else 1, -n.confidence))
        if not ready:
            return None
        ready[0].status = "live"
        return ready[0]

    def resolve(self, node_id: str, ok: bool, confidence: float | None = None) -> None:
        node = self.nodes[node_id]
        node.status = "pass" if ok else "fail"
        if confidence is not None:
            node.confidence = confidence
        self._refresh()
