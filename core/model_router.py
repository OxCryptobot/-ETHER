"""Model scale plane: local FAST 4B, local-large when VRAM allows, outsource when keyed.

FAST/living stay local unless ETHER_OUTSOURCE_FAST=1.
LIVE can take a bigger local model or an OpenAI-compatible outsource (Grok/xAI/OpenAI).
Does not call the network by itself — Rose Quartz / burst do.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "model_router.json"

FAST_MODEL = os.getenv("ETHER_FAST_MODEL", "qwen3.5:4b-q4_K_M")
LIVE_MODEL = os.getenv("ETHER_LIVE_MODEL", os.getenv("ETHER_BURST_MODEL", FAST_MODEL))
MEASURE_MODEL = os.getenv("ETHER_MEASURE_MODEL", FAST_MODEL)
LOCAL_LARGE = os.getenv("ETHER_LOCAL_LARGE_MODEL", LIVE_MODEL)
OUTSOURCE_MODEL = (
    os.getenv("ETHER_OUTSOURCE_MODEL")
    or os.getenv("ETHER_BURST_MODEL")
    or "grok-3"
)
VRAM_LARGE_MB = int(os.getenv("ETHER_VRAM_LARGE_MB", "12000"))


def outsource_configured() -> bool:
    return bool(
        os.getenv("ETHER_OUTSOURCE_API_KEY")
        or os.getenv("ETHER_BURST_API_KEY")
        or os.getenv("XAI_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
    )


def vram_mb() -> int:
    env = os.getenv("ETHER_VRAM_MB", "").strip()
    if env:
        try:
            return int(env)
        except ValueError:
            pass
    path = ROOT / "artifacts" / "host_agent_status.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return int((data.get("gpu") or {}).get("mem_total_mb") or 0)
    except Exception:
        return 0


def select_model(job_or_class: Any = "fast") -> Dict[str, Any]:
    if isinstance(job_or_class, dict):
        cls = str(job_or_class.get("class") or "").lower()
        note = str(job_or_class.get("note") or "").lower()
        jid = str(job_or_class.get("id") or "").lower()
        hay = f"{cls} {note} {jid}"
    else:
        hay = str(job_or_class or "fast").lower()

    if "live" in hay and "scripted" not in hay:
        model = LIVE_MODEL
        lane = "live"
    elif any(x in hay for x in ("measure", "honest", "soft_launch", "kpi")):
        model = MEASURE_MODEL
        lane = "measure"
    else:
        model = FAST_MODEL
        lane = "fast"

    return {
        "model": model,
        "lane": lane,
        "fast_model": FAST_MODEL,
        "live_model": LIVE_MODEL,
        "note": "Dual-lane router; wire via ETHER_FAST_MODEL / ETHER_LIVE_MODEL",
    }


def outsource_wanted(lane: str) -> bool:
    if not outsource_configured():
        return False
    if os.getenv("ETHER_OUTSOURCE_FAST", "0") == "1" and lane == "fast":
        return True
    if os.getenv("ETHER_OUTSOURCE", "0") == "1" and lane in ("live", "measure"):
        return True
    if os.getenv("ETHER_BURST", "0") == "1" and lane == "live":
        return True
    return False


def select_backend(job_or_class: Any = "fast", vram: Optional[int] = None) -> Dict[str, Any]:
    sel = select_model(job_or_class)
    mem = int(vram) if vram is not None else vram_mb()
    if outsource_wanted(sel["lane"]):
        sel.update(
            {
                "backend": "outsource",
                "model": OUTSOURCE_MODEL,
                "scalable": True,
                "reason": "outsource_keyed",
            }
        )
        return sel
    if mem >= VRAM_LARGE_MB and sel["lane"] in ("live", "measure"):
        sel.update(
            {
                "backend": "ollama",
                "model": LOCAL_LARGE,
                "scalable": True,
                "reason": "local_large_vram",
                "vram_mb": mem,
            }
        )
        return sel
    sel.update({"backend": "ollama", "scalable": False, "reason": "local_fast", "vram_mb": mem})
    return sel


def status() -> Dict[str, Any]:
    samples = {
        "fast": select_backend("fast"),
        "live": select_backend({"class": "live", "note": "live attempt"}),
        "measure": select_backend("measure_tick"),
        "scripted": select_backend({"class": "fast", "note": "scripted hard"}),
    }
    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "fast_model": FAST_MODEL,
        "live_model": LIVE_MODEL,
        "measure_model": MEASURE_MODEL,
        "local_large": LOCAL_LARGE,
        "outsource_model": OUTSOURCE_MODEL,
        "outsource_configured": outsource_configured(),
        "vram_mb": vram_mb(),
        "samples": samples,
        "note": "Scale plane: local 4B default; local-large on VRAM; outsource when keyed. Living FAST stays local.",
    }
    try:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    except Exception:
        pass
    return payload
