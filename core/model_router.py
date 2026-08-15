"""Moonshot 17 — Model router by latency class.

FAST/scripted → local small model; LIVE → burst model.
Does not force Ollama calls — exposes selection for Pipeline/Rose Quartz.
"""
from __future__ import annotations

import os
from typing import Any, Dict

FAST_MODEL = os.getenv("ETHER_FAST_MODEL", "qwen3.5:4b-q4_K_M")
LIVE_MODEL = os.getenv("ETHER_LIVE_MODEL", os.getenv("ETHER_BURST_MODEL", FAST_MODEL))
MEASURE_MODEL = os.getenv("ETHER_MEASURE_MODEL", FAST_MODEL)


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


def status() -> Dict[str, Any]:
    return {
        "fast_model": FAST_MODEL,
        "live_model": LIVE_MODEL,
        "measure_model": MEASURE_MODEL,
    }
