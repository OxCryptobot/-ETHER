"""Pick the strongest available local coder model — learning quality floor."""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

# Preference order: stronger first. Tags must match `ollama list` names.
PREFERRED = [
    "qwen2.5-coder:32b",
    "qwen2.5-coder:14b",
    "qwen2.5-coder:7b",
    "deepseek-coder-v2:16b",
    "deepseek-coder:6.7b",
    "codellama:13b",
    "qwen2.5-coder:3b",
    "deepseek-coder:1.3b",
    "llama3.2:3b",
]


def _ollama_tags(base: str) -> List[str]:
    url = base.rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        names = []
        for m in data.get("models") or []:
            n = m.get("name") or m.get("model") or ""
            if n:
                names.append(n)
        return names
    except Exception:
        return []


def _match(preferred: str, available: List[str]) -> Optional[str]:
    pref = preferred.lower()
    for a in available:
        al = a.lower()
        if al == pref or al.startswith(pref) or pref in al:
            return a
    # family match e.g. qwen2.5-coder:14b vs qwen2.5-coder:14b-instruct
    family = pref.split(":")[0]
    size = pref.split(":")[1] if ":" in pref else ""
    for a in available:
        al = a.lower()
        if family in al and (not size or size in al):
            return a
    return None


def select_primary_model(force_refresh: bool = False) -> Dict[str, Any]:
    """Return chosen model; set ETHER_PRIMARY_MODEL if empty or ETHER_AUTO_MODEL=1."""
    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    auto = os.getenv("ETHER_AUTO_MODEL", "1") == "1"
    current = (os.getenv("ETHER_PRIMARY_MODEL") or "").strip()
    available = _ollama_tags(base)

    chosen = None
    reason = "env"
    if current and not auto and not force_refresh:
        chosen = current
        reason = "ETHER_PRIMARY_MODEL"
    else:
        for pref in PREFERRED:
            m = _match(pref, available)
            if m:
                chosen = m
                reason = f"auto:{pref}"
                break
        if not chosen and available:
            chosen = available[0]
            reason = "first_available"
        if not chosen:
            chosen = current or "qwen2.5-coder:3b"
            reason = "fallback_default"

    if auto or not current:
        os.environ["ETHER_PRIMARY_MODEL"] = chosen

    return {
        "model": chosen,
        "reason": reason,
        "available": available[:20],
        "auto": auto,
        "base": base,
    }


def ensure_model_env() -> str:
    return str(select_primary_model().get("model") or "")
