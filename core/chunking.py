"""Smart code chunking for Citrine indexing."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List


def chunk_python_source(
    text: str,
    path: str = "",
    max_chars: int = 1200,
    overlap: int = 100,
) -> List[Dict[str, Any]]:
    """Split Python source into function/class-aware chunks.

    Falls back to sliding windows for non-structured text.
    """
    if not text or not text.strip():
        return []

    # Prefer structural splits on top-level def/class
    pattern = re.compile(r"^(?=def |class |async def )", re.MULTILINE)
    parts = pattern.split(text)
    chunks: List[Dict[str, Any]] = []

    if len(parts) > 1:
        # parts[0] may be module preamble
        preamble = parts[0].strip()
        if preamble:
            chunks.extend(_window(preamble, path, max_chars, overlap, kind="module"))
        for part in parts[1:]:
            block = part.strip()
            if not block:
                continue
            kind = "class" if block.startswith("class ") else "function"
            name = _first_name(block)
            if len(block) <= max_chars:
                chunks.append(
                    {
                        "text": block,
                        "metadata": {
                            "path": path,
                            "kind": kind,
                            "symbol": name,
                        },
                    }
                )
            else:
                for c in _window(block, path, max_chars, overlap, kind=kind):
                    c["metadata"]["symbol"] = name
                    chunks.append(c)
        return chunks

    return _window(text, path, max_chars, overlap, kind="text")


def chunk_file(path: Path, max_chars: int = 1200) -> List[Dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    rel = str(path).replace("\\", "/")
    if path.suffix == ".py":
        return chunk_python_source(text, path=rel, max_chars=max_chars)
    return _window(text, rel, max_chars, 80, kind="text")


def _first_name(block: str) -> str:
    m = re.match(r"(?:async\s+)?def\s+(\w+)|class\s+(\w+)", block)
    if not m:
        return ""
    return m.group(1) or m.group(2) or ""


def _window(
    text: str,
    path: str,
    max_chars: int,
    overlap: int,
    kind: str,
) -> List[Dict[str, Any]]:
    text = text.strip()
    if not text:
        return []
    out: List[Dict[str, Any]] = []
    i = 0
    n = len(text)
    while i < n:
        piece = text[i : i + max_chars]
        out.append({"text": piece, "metadata": {"path": path, "kind": kind, "offset": i}})
        if i + max_chars >= n:
            break
        i += max(1, max_chars - overlap)
    return out
