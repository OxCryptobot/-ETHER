"""4B context budget. Symbol hits plus named files. Nothing else."""
from __future__ import annotations

import os


def context_char_budget(model_ctx: int | None = None) -> int:
    ctx = model_ctx or int(os.getenv("ETHER_MODEL_CTX") or "8192")
    tokens = min(int(ctx * 0.35), 1800)
    return max(800, tokens * 4)


def pack(root, query: str, files: list[str] | None = None, max_chars: int | None = None) -> str:
    """Symbol hits plus the named files. Nothing else. Fits a 4B budget."""
    from pathlib import Path

    root = Path(root)
    budget = max_chars if max_chars is not None else context_char_budget()
    parts: list[str] = []
    try:
        from core.symbol_index import format_block

        sym = format_block(query, root=root, k=6, max_chars=min(600, max(200, budget // 3)))
        if sym:
            parts.append(sym)
    except Exception:
        pass
    used = sum(len(p) for p in parts)
    for rel in files or []:
        path = root / rel
        if not path.is_file():
            continue
        body = path.read_text(encoding="utf-8", errors="ignore")[:800]
        chunk = f"### {rel}\n{body}"
        if used + len(chunk) > budget:
            break
        parts.append(chunk)
        used += len(chunk)
    return "\n\n".join(parts)[:budget]