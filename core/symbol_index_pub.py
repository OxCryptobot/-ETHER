"""Publish a small symbol-index snapshot for observability.

Does not change default pipeline behavior (ETHER_SYMBOL_INDEX still opt-in).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "symbol_index.json"


def publish(query: str = "pipeline tool_runtime host_agent") -> Dict[str, Any]:
    from core.symbol_index import index_tree, rank, symbol_index_enabled

    entries = index_tree(ROOT, max_files=120)
    hits = rank(entries, query, k=8)
    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "enabled_flag": symbol_index_enabled(),
        "n_files": len(entries),
        "n_with_symbols": sum(1 for e in entries if e.symbols),
        "query": query,
        "top": [
            {"score": sc, "path": e.path, "symbols": e.symbols[:8]} for sc, e in hits
        ],
        "note": "Snapshot only. Pipeline uses index only when ETHER_SYMBOL_INDEX=1.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(publish(), indent=2))
