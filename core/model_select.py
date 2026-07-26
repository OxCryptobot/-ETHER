"""Pick local coder model constrained by hardware profile (host vs cousin)."""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "config" / "hardware_profile.json"

# High-end / cousin preference (only used when profile=cousin)
PREFERRED_COUSIN = [
    "qwen2.5-coder:32b",
    "qwen2.5-coder:14b",
    "qwen2.5-coder:7b",
    "deepseek-coder-v2:16b",
    "deepseek-coder:6.7b",
    "codellama:13b",
    "qwen2.5-coder:3b",
    "phi3:mini",
    "deepseek-coder:1.3b",
    "llama3.2:3b",
]

# Owner host (GTX 1650 4GB / 12GB RAM) — never prefer >3B class
PREFERRED_HOST = [
    "qwen2.5-coder:3b",
    "phi3:mini",
    "qwen2.5-coder:1.5b",
    "llama3.2:3b",
    "deepseek-coder:1.3b",
]

_SIZE_MARKERS_HEAVY = ("32b", "14b", "13b", "16b", "7b", "6.7b", "8b", "9b")


def load_profile() -> Dict[str, Any]:
    env = (os.getenv("ETHER_HW_PROFILE") or "").strip().lower()
    data: Dict[str, Any] = {}
    if PROFILE_PATH.exists():
        try:
            data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    profile = env or str(data.get("profile") or "host").lower()
    if profile not in ("host", "cousin", "auto"):
        profile = "host"
    preferred = list(data.get("preferred_models") or [])
    if profile == "cousin":
        preferred = preferred or PREFERRED_COUSIN
    else:
        # host default — ignore cousin-sized entries if someone edited JSON badly
        preferred = preferred or PREFERRED_HOST
        preferred = [m for m in preferred if not _is_heavy(m)]
        if not preferred:
            preferred = list(PREFERRED_HOST)
    return {
        "profile": profile if profile != "auto" else "host",
        "preferred": preferred,
        "max_param_b": int(data.get("max_param_b") or (3 if profile != "cousin" else 32)),
        "label": data.get("label") or profile,
    }


def _is_heavy(name: str) -> bool:
    n = name.lower()
    return any(m in n for m in _SIZE_MARKERS_HEAVY)


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
    family = pref.split(":")[0]
    size = pref.split(":")[1] if ":" in pref else ""
    for a in available:
        al = a.lower()
        if family in al and (not size or size in al):
            return a
    return None


def select_primary_model(force_refresh: bool = False) -> Dict[str, Any]:
    """Choose model under hardware cap. Host never auto-selects 7B+."""
    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    auto = os.getenv("ETHER_AUTO_MODEL", "1") == "1"
    current = (os.getenv("ETHER_PRIMARY_MODEL") or "").strip()
    available = _ollama_tags(base)
    prof = load_profile()
    preferred = list(prof["preferred"])

    # Filter available by profile cap
    if prof["profile"] != "cousin":
        available_safe = [a for a in available if not _is_heavy(a)]
    else:
        available_safe = list(available)

    chosen = None
    reason = "env"
    if current and not auto and not force_refresh:
        # Respect explicit env but warn if heavy on host
        if prof["profile"] != "cousin" and _is_heavy(current):
            reason = "env_heavy_ignored_host"
            current = ""
        else:
            chosen = current
            reason = "ETHER_PRIMARY_MODEL"

    if not chosen:
        for pref in preferred:
            m = _match(pref, available_safe if available_safe else available)
            if m:
                chosen = m
                reason = f"profile:{prof['profile']}:{pref}"
                break
        if not chosen and available_safe:
            chosen = available_safe[0]
            reason = "first_safe_available"
        if not chosen and available:
            # last resort: anything non-heavy
            for a in available:
                if not _is_heavy(a):
                    chosen = a
                    reason = "any_non_heavy"
                    break
        if not chosen:
            chosen = "qwen2.5-coder:3b"
            reason = "fallback_host_3b"

    if auto or not (os.getenv("ETHER_PRIMARY_MODEL") or "").strip():
        os.environ["ETHER_PRIMARY_MODEL"] = chosen

    return {
        "model": chosen,
        "reason": reason,
        "profile": prof["profile"],
        "label": prof.get("label"),
        "max_param_b": prof.get("max_param_b"),
        "available": available[:20],
        "auto": auto,
        "base": base,
    }


def ensure_model_env() -> str:
    return str(select_primary_model().get("model") or "qwen2.5-coder:3b")
