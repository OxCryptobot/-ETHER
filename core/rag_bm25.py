"""Offline repo RAG — BM25-style lexical retrieval (no Qdrant required)."""

from __future__ import annotations

import math
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".venv", "node_modules", ".git", "__pycache__", "memory", ".mypy_cache", ".ruff_cache"}


def rag_enabled() -> bool:
    return os.getenv("ETHER_RAG_BM25", "1") == "1"


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", (text or "").lower())


def _iter_py_files(root: Path) -> List[Path]:
    out: List[Path] = []
    for p in root.rglob("*.py"):
        if any(part in SKIP for part in p.parts):
            continue
        out.append(p)
    return out[:400]


def _chunk_file(path: Path, max_chars: int = 1200) -> List[Tuple[str, str]]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    chunks: List[Tuple[str, str]] = []
    lines = text.splitlines()
    buf: List[str] = []
    size = 0
    start = 1
    for i, line in enumerate(lines, 1):
        buf.append(line)
        size += len(line) + 1
        if size >= max_chars:
            chunk = "\n".join(buf)
            chunks.append((f"{rel}:{start}-{i}", chunk))
            buf, size, start = [], 0, i + 1
    if buf:
        chunks.append((f"{rel}:{start}-{len(lines)}", "\n".join(buf)))
    return chunks


def build_index(root: Path | None = None) -> Dict:
    root = root or ROOT
    docs: List[Tuple[str, str, Counter]] = []
    df: Counter = Counter()
    for path in _iter_py_files(root):
        for loc, chunk in _chunk_file(path):
            toks = _tokenize(chunk)
            if len(toks) < 5:
                continue
            tf = Counter(toks)
            docs.append((loc, chunk, tf))
            for t in tf:
                df[t] += 1
    return {"docs": docs, "df": df, "n": len(docs)}


def search(query: str, k: int = 4, root: Path | None = None) -> List[Dict]:
    if not rag_enabled():
        return []
    idx = build_index(root)
    docs = idx["docs"]
    df: Counter = idx["df"]
    n = max(1, idx["n"])
    q = Counter(_tokenize(query))
    if not q or not docs:
        return []
    scored = []
    for loc, chunk, tf in docs:
        score = 0.0
        dl = sum(tf.values()) or 1
        for term, qf in q.items():
            if term not in tf:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            # BM25-ish
            tf_n = tf[term]
            score += idf * (tf_n * 2.2) / (tf_n + 1.2 * (0.25 + 0.75 * dl / 200.0)) * qf
        if score > 0:
            scored.append((score, loc, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {"score": round(s, 4), "loc": loc, "text": chunk[:900]}
        for s, loc, chunk in scored[:k]
    ]


def format_block(query: str, k: int = 4) -> str:
    hits = search(query, k=k)
    if not hits:
        return ""
    parts = [f"[{h['score']}] {h['loc']}\n{h['text']}" for h in hits]
    return "\n\n".join(parts)[:3000]
