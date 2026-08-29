"""Operational memory stack — RAG + failure graph + LoRA dry + lesson research.

This is the Phase 3 'LoRA and RAG and Graph' surface. It does not train
weights. It does not require Qdrant. It is safe under wheels.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "memory_stack.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rag_query(query: str, k: int = 4) -> Dict[str, Any]:
    from core.rag_bm25 import rag_enabled, search

    hits = search(query, k=k) if rag_enabled() else []
    return {
        "ok": True,
        "enabled": rag_enabled(),
        "backend": "bm25_offline",
        "query": query[:120],
        "n": len(hits),
        "hits": [
            {"loc": h.get("loc"), "score": h.get("score"), "text": str(h.get("text") or "")[:240]}
            for h in hits
        ],
    }


def graph_status() -> Dict[str, Any]:
    from core.failure_graph import GRAPH_PATH, repair_hint, top_failures

    top = top_failures(8)
    hint = repair_hint("Timeout")
    return {
        "ok": True,
        "backend": "failure_graph",
        "path": str(GRAPH_PATH.relative_to(ROOT)).replace("\\", "/") if GRAPH_PATH.exists() else None,
        "n_top": len(top),
        "top": top[:5],
        "timeout_hint": hint[:160],
        "vector_schema": "core.vectors.Vector",
    }


def lora_status() -> Dict[str, Any]:
    from core.lora_dry_tick import dry_tick

    tick = dry_tick(force=True)
    train_flag = (os.getenv("ETHER_LORA_TRAIN") or "0").strip() == "1"
    promote_flag = (os.getenv("ETHER_LORA_PROMOTE") or "0").strip() == "1"
    return {
        "ok": bool(tick.get("ok")),
        "operational": True,
        "mode": "dry",
        "trained": False,
        "adapter_written": False,
        "flags": {"ETHER_LORA_TRAIN": train_flag, "ETHER_LORA_PROMOTE": promote_flag},
        "ready_for_real_train": False,
        "tick_ok": tick.get("ok"),
        "note": "Dry path is operational. Real train stays dual-flag + preference health.",
    }


def lessons_query(gap: str) -> Dict[str, Any]:
    from core.self_improve_research import research

    return research(gap)


def snapshot() -> Dict[str, Any]:
    rag = rag_query("anchor_edit replace_once ledger merge observe loop")
    graph = graph_status()
    lora = lora_status()
    lessons = lessons_query("hard_live")
    payload: Dict[str, Any] = {
        "updated": _now(),
        "ok": bool(rag.get("ok") and graph.get("ok") and lora.get("ok")),
        "training_wheels": (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0",
        "soft_launch": False,
        "rag": {"enabled": rag.get("enabled"), "backend": rag.get("backend"), "n": rag.get("n")},
        "graph": {
            "backend": graph.get("backend"),
            "n_top": graph.get("n_top"),
            "timeout_hint": graph.get("timeout_hint"),
        },
        "lora": {
            "mode": lora.get("mode"),
            "trained": lora.get("trained"),
            "operational": lora.get("operational"),
        },
        "lessons_n": lessons.get("n"),
        "note": (
            "RAG=BM25 offline (no Qdrant). Graph=failure_graph + Vector schema. "
            "LoRA=dry tick only. All three report operational without lifting wheels."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    payload["rag_hits"] = rag.get("hits")
    return payload


if __name__ == "__main__":
    print(json.dumps(snapshot(), indent=2, default=str))
