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
    "qwen3.5:4b",
    "qwen2.5-coder:3b",
    "phi3:mini",
    "deepseek-coder:1.3b",
    "llama3.2:3b",
]

# Owner host (GTX 1650 4GB / 12GB RAM) — Q4_K_M only, never >4B class.
# ollama library qwen3.5:4b is already file_type=Q4_K_M (3.4GB).
# Prefer SHORT tag first so LIVE never 404s when quant tag is absent from tags.
PREFERRED_HOST = [
    "qwen3.5:4b",
    "qwen3.5:4b-q4_K_M",
    "qwen3.5:4b-instruct",
    "qwen3:4b",
    "qwen2.5-coder:3b",
    "phi3:mini",
    "qwen2.5-coder:1.5b",
    "llama3.2:3b",
    "deepseek-coder:1.3b",
]

_SIZE_MARKERS_HEAVY = (
    "6.7b", "7b", "8b", "9b", "13b", "14b", "16b",
    # Everything above 16B was missing, so 20b/22b/27b/33b/34b/35b/70b/72b all
    # reported as within a 3B host cap. ("27b" only matched by accident,
    # because it contains "7b".)
    "20b", "22b", "24b", "27b", "30b", "32b", "33b", "34b", "35b", "40b",
    "65b", "70b", "72b", "104b", "180b", "397b", "405b",
)

# Not code models. Selecting one of these as the generator produces garbage
# for every objective; an embedding model was in fact being chosen.
_NON_CODER_MARKERS = ("embed", "rerank", "bge", "nomic", "minilm", "clip", "whisper")


def _is_non_coder(name: str) -> bool:
    n = (name or "").lower()
    return any(m in n for m in _NON_CODER_MARKERS)


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
        "max_param_b": int(data.get("max_param_b") or (4 if profile != "cousin" else 32)),
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

    # Embedding/reranker tags can never be the code generator, on any profile.
    available = [a for a in available if not _is_non_coder(a)]

    # Filter available by profile cap
    if prof["profile"] != "cousin":
        available_safe = [a for a in available if not _is_heavy(a)]
    else:
        available_safe = list(available)

    chosen = None
    reason = "env"
    if current and not auto and not force_refresh:
        # Respect explicit env but only if it is actually available (or heavy-ignored).
        if prof["profile"] != "cousin" and _is_heavy(current):
            reason = "env_heavy_ignored_host"
            current = ""
        else:
            # If the exact env tag is missing from Ollama, fall through to preferred
            # so LIVE does not hard-fail on a stale quant tag in .env.
            if available and current not in available and not any(
                a.lower() == current.lower() or a.lower().startswith(current.lower())
                for a in available
            ):
                reason = "env_tag_missing_fallthrough"
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
            chosen = "qwen3.5:4b"
            reason = "fallback_host_4b"

    # Only fill in a model when the operator has not chosen one. This used to
    # overwrite an explicit ETHER_PRIMARY_MODEL whenever ETHER_AUTO_MODEL was
    # set (it defaults to "1"), and the sole caller is the dashboard's
    # read-only status probe (core/infra_status.py). Because the daemon runs
    # uvicorn in-process and passes os.environ to every child, merely polling
    # the dashboard could silently repoint code generation at whatever this
    # picked — observed selecting `nomic-embed-text`, an embedding model.
    # A status probe must not reconfigure the system it is reporting on.
    if not (os.getenv("ETHER_PRIMARY_MODEL") or "").strip():
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
    return str(select_primary_model().get("model") or "qwen3.5:4b")


def resolved_primary(explicit: Optional[str] = None) -> str:
    """Single source of truth for Rose, multi_llm, and measure scripts.

    Never silently default to qwen2.5-coder:3b. Host cap stays ≤4B.
    """
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    env = (os.getenv("ETHER_PRIMARY_MODEL") or "").strip()
    if env:
        return env
    return ensure_model_env()


def resolved_fallback(explicit: Optional[str] = None) -> str:
    """Host must not fall through to an 8B (deepseek-r1:8b used to)."""
    env = (os.getenv("ETHER_FALLBACK_MODEL") or "").strip()
    cand = (explicit or env or "").strip()
    prof = load_profile()
    if cand and prof.get("profile") != "cousin" and _is_heavy(cand):
        return resolved_primary()
    if cand:
        return cand
    return resolved_primary()


def host_num_ctx() -> int:
    """4GB KV: 4096 is the host default. 32768 was a silent VRAM tax."""
    raw = (os.getenv("ETHER_NUM_CTX") or "").strip()
    if raw:
        try:
            return max(512, int(raw))
        except ValueError:
            pass
    if load_profile().get("profile") == "cousin":
        return 8192
    return 4096
