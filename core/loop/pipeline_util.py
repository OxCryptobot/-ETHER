"""Tiny helpers peeled off pipeline.py. Keep Pipeline.run a walker."""
from __future__ import annotations

import os
import re


def is_burst_model(model_used: str) -> bool:
    """True only for the configured burst/cloud model, not local llama-family."""
    m = (model_used or "").strip().lower()
    if not m:
        return False
    configured = (os.getenv("ETHER_BURST_MODEL") or "grok-3").strip().lower()
    return m in {configured, "burst"}


def looks_multifile(objective: str) -> bool:
    o = (objective or "").lower()
    return bool(
        re.search(
            r"\b(class|module|package|refactor|file|project|codebase|multi[- ]?file)\b",
            o,
        )
        or ".py" in o
    )


def strip_fences(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.split("\n")[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines)
    return text
