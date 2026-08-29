"""Phase 3+ completeness board — what is built vs what is still a flag."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "phase3_complete.json"


def _ok(mod: str, attr: str) -> bool:
    try:
        m = __import__(mod, fromlist=[attr])
        return callable(getattr(m, attr, None)) or getattr(m, attr, None) is not None
    except Exception:
        return False


def compute() -> Dict[str, Any]:
    items: List[Dict[str, Any]] = [
        {"id": "dual_window", "name": "Dual-window protocol", "ok": _ok("core.dual_window", "submit_proposal")},
        {"id": "self_improve", "name": "Self-improve cycle", "ok": _ok("core.self_improve", "cycle")},
        {"id": "rag", "name": "RAG BM25", "ok": _ok("core.rag_bm25", "search")},
        {"id": "graph", "name": "Failure graph", "ok": _ok("core.failure_graph", "repair_hint")},
        {"id": "lora_dry", "name": "LoRA dry tick", "ok": _ok("core.lora_dry_tick", "dry_tick")},
        {"id": "langchain", "name": "LangChain adapter", "ok": _ok("core.langchain_adapter", "run_chain")},
        {"id": "evolve", "name": "Phase 3 evolve operator", "ok": _ok("core.phase3_evolve", "tick")},
        {"id": "memory_stack", "name": "Memory stack facade", "ok": _ok("core.memory_stack", "snapshot")},
        {"id": "mutate_tools", "name": "Hard LIVE mutate tools", "ok": _ok("core.hard_live_tools", "anchor_edit")},
        {"id": "observe_breaker", "name": "Observe-loop killer", "ok": _ok("core.observe_breaker", "rewrite")},
    ]
    done = sum(1 for i in items if i["ok"])
    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "phase": "3+",
        "n": len(items),
        "passed": done,
        "pct": round(100.0 * done / max(1, len(items))),
        "ok": done == len(items),
        "items": items,
        "soft_launch": False,
        "lora_train": False,
        "note": "Module surface complete != product unleashed. See unleash_check.json.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
