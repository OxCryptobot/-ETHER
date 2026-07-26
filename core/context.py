"""Workspace context + offline BM25 RAG (Citrine-lite without Qdrant)."""

from __future__ import annotations

import os
from pathlib import Path


def context_enabled() -> bool:
    return os.getenv("ETHER_CONTEXT", "1") == "1"


def gather_workspace_context(root: Path, query: str = "", max_chars: int = 3500) -> str:
    parts: list[str] = []
    # BM25 offline RAG first — strongest signal vs Cursor gap
    if os.getenv("ETHER_RAG_BM25", "1") == "1" and query:
        try:
            from core.rag_bm25 import format_block

            block = format_block(query, k=4)
            if block:
                parts.append("### Repo BM25 hits\n" + block)
        except Exception:
            pass

    # light path: list key package files
    try:
        for rel in ("core", "gems", "scripts", "cli"):
            d = root / rel
            if not d.is_dir():
                continue
            files = sorted(d.rglob("*.py"))[:12]
            listing = ", ".join(str(f.relative_to(root)) for f in files)
            if listing:
                parts.append(f"### {rel}/\n{listing}")
    except Exception:
        pass

    text = "\n\n".join(parts)
    return text[:max_chars]
