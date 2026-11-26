"""Pinned answers for the operator. Published so the dashboard can show them."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "operator_answers.json"

ANSWERS: Dict[str, str] = {
    "soft_launch": (
        "Available the moment ETHER_SOFT_LAUNCH=1 is set on the Windows host AND "
        "merge LIVE is repeatable (p1_248 still failed observe-loop). Eligible rate "
        "1.0 is not the soft-launch gate. Repeatable hard LIVE is."
    ),
    "websocket": (
        "Dashboard already has WebSocket /ws on 127.0.0.1:8787 for the Control Matrix. "
        "Grok (this tutor) does not sit on your LAN. A socket from this cloud session "
        "to your PC would be a tunnel you did not open. Git outbox/inbox is the tutor wire "
        "that already works across that gap."
    ),
    "qdrant": (
        "qdrant-client is already a dependency. A Qdrant server is another process on "
        "12GB RAM next to Ollama 4B. BM25 is the operational RAG today. Point "
        "ETHER_QDRANT_URL at a server when you run one; retrieval degrades to BM25 if down."
    ),
    "neo4j": (
        "failure_graph is 300 bounded nodes of stderr signatures. Neo4j adds JVM + disk "
        "for a lookup table we already persist as JSON. Use it when we have multi-agent "
        "edges that need Cypher. Not tonight's bottleneck."
    ),
    "lora_weights": (
        "GTX 1650 has 4GB. The 4B Q4 model already occupies most of it. A real LoRA train "
        "needs PEFT/Unsloth + preference pairs + free VRAM. Dry path is operational. "
        "Flags ETHER_LORA_TRAIN=1 and ETHER_LORA_PROMOTE=1 turn on train_adapter. "
        "Without pairs and VRAM it OOMs, it does not evolve."
    ),
    "langchain_host": (
        "Adapter is in-tree. The extra is optional so the default venv stays small. "
        "p3_22 pip-installs ether[langchain] on the host. Chain already runs without the extra."
    ),
    "hard_live": (
        "Best method we have: numbered read, bug_comments, anchor_edit/replace_once, "
        "observe-loop rewrite at 3 and kill at 5. p1_242 proved merge LIVE can pass. "
        "p1_248 proved the 4B still prefers read_file when the breaker is only a hint. "
        "Babysitting is SEED_DENY so those fails cannot fake the 1.0 rate."
    ),
}


def publish() -> Dict[str, Any]:
    payload = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "answers": ANSWERS,
        "soft_launch_available": False,
        "next_gate": "repeatable hard LIVE merge (not eligible greeter)",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(publish(), indent=2))
