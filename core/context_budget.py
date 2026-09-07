"""Moonshot 14 — Context budget meter. F07: 4k-token cap for 4B."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "context_budget.json"
MAX_TOKENS = int(os.getenv("ETHER_CONTEXT_MAX_TOKENS", "4000"))
MAX_CHARS = int(os.getenv("ETHER_CONTEXT_MAX_CHARS", str(MAX_TOKENS * 4)))


def estimate_tokens(text: str) -> int:
    return max(0, len(text or "") // 4)


def _grade(out_chars: int, max_chars: int, ratio: Optional[float]) -> str:
    if out_chars > max_chars:
        return "OVER"
    util = out_chars / max_chars if max_chars else 0.0
    if util >= 0.9:
        return "HOT"
    if util >= 0.7:
        return "WARM"
    if ratio is not None and ratio < 0.35:
        return "COMPRESSED"
    return "OK"


def measure(text: str = "", *, query: str = "", max_chars: Optional[int] = None) -> Dict[str, Any]:
    max_chars = max_chars or MAX_CHARS
    raw_chars = len(text or "")
    compressed = text or ""
    try:
        from core.context import compress_text

        compressed = compress_text(text or "", query=query, max_chars=max_chars)
    except Exception:
        compressed = (text or "")[:max_chars]
    out_chars = len(compressed)
    ratio = round(out_chars / raw_chars, 4) if raw_chars else None
    util = round(out_chars / max_chars, 4) if max_chars else None
    grade = _grade(out_chars, max_chars, ratio)
    payload = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "raw_chars": raw_chars,
        "out_chars": out_chars,
        "max_chars": max_chars,
        "max_tokens": MAX_TOKENS,
        "raw_tokens_est": estimate_tokens(text or ""),
        "out_tokens_est": estimate_tokens(compressed),
        "compress_ratio": ratio,
        "utilization": util,
        "grade": grade,
        "over_budget": out_chars > max_chars,
        "status": grade,
        "note": "F07 4k-token cap. tokens ~4 chars. grade=OK|WARM|HOT|OVER|COMPRESSED",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


def publish_sample() -> Dict[str, Any]:
    sample = ""
    for rel in ("STATUS.md", "core/pipeline.py", "core/context.py", "core/loop/generate_retry_loop.py"):
        p = ROOT / rel
        if p.exists():
            try:
                sample += p.read_text(encoding="utf-8")[:8000] + "\n"
            except Exception:
                pass
    return measure(sample, query="coding agent context")


if __name__ == "__main__":
    print(json.dumps(publish_sample(), indent=2))
