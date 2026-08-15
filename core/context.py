"""Workspace context + offline BM25 RAG + extractive compress v0.

Citrine-lite without Qdrant. Compress ranks paragraphs by query term
overlap and fits a hard char budget (poisoning defense + token discipline).
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Tuple


def context_enabled() -> bool:
    return os.getenv("ETHER_CONTEXT", "1") == "1"


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", (text or "").lower())


def compress_text(
    text: str,
    *,
    query: str = "",
    max_chars: int = 3500,
) -> str:
    """Extractive compress v0: keep highest-overlap paragraphs under budget.

    If no query, prefers head + tail slices (common in coding prompts).
    Never exceeds max_chars.
    """
    text = (text or "").strip()
    if not text:
        return ""
    if len(text) <= max_chars:
        return text

    # Split on blank lines; fall back to fixed windows
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paras) <= 1:
        paras = [text[i : i + 400] for i in range(0, len(text), 400)]

    q_terms = set(_tokenize(query))
    scored: List[Tuple[float, int, str]] = []
    for i, p in enumerate(paras):
        if not q_terms:
            # head/tail bias without query
            score = 2.0 if i < 2 or i >= len(paras) - 2 else 1.0
        else:
            toks = set(_tokenize(p))
            overlap = len(q_terms & toks)
            score = float(overlap) + (0.15 if i < 3 else 0.0)
        scored.append((score, i, p))

    scored.sort(key=lambda x: (-x[0], x[1]))
    chosen: List[Tuple[int, str]] = []
    used = 0
    for score, i, p in scored:
        chunk = p if len(p) <= 900 else p[:900]
        cost = len(chunk) + (2 if chosen else 0)
        if used + cost > max_chars:
            remain = max_chars - used - 2
            if remain > 80:
                chosen.append((i, chunk[:remain]))
                used += remain + 2
            break
        chosen.append((i, chunk))
        used += cost
        if used >= max_chars:
            break

    chosen.sort(key=lambda x: x[0])  # restore document order
    out = "\n\n".join(c for _, c in chosen)
    return out[:max_chars]


def gather_workspace_context(root: Path, query: str = "", max_chars: int = 3500) -> str:
    if not context_enabled():
        return ""
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
    if os.getenv("ETHER_CONTEXT_COMPRESS", "1") == "1":
        return compress_text(text, query=query, max_chars=max_chars)
    return text[:max_chars]
