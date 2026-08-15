"""Job class contract — FAST vs LIVE for host multi-job scheduling (P2).

Host can prefer FAST jobs when LIVE is on cooldown or GPU is busy.
Jobs may set "class": "fast" | "live" | "any".
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

FAST = "fast"
LIVE = "live"
ANY = "any"


def normalize_class(raw: Any) -> str:
    s = str(raw or ANY).strip().lower()
    if s in (FAST, "scripted", "measure", "gate", "pytest"):
        return FAST
    if s in (LIVE, "pipeline_live", "llm"):
        return LIVE
    return ANY


def job_class(job: Dict[str, Any]) -> str:
    if "class" in job:
        return normalize_class(job.get("class"))
    note = str(job.get("note") or "").lower()
    jid = str(job.get("id") or "").lower()
    hay = note + " " + jid
    if any(x in hay for x in ("live", "pipeline_ledger", "ss_pipeline_ledger")):
        return LIVE
    if any(x in hay for x in ("scripted", "pytest", "ruff", "pep8", "whats_next", "archive")):
        return FAST
    return ANY


def pick_next(
    pending: Iterable[Dict[str, Any]],
    *,
    prefer_fast: bool = False,
    skip_live: bool = False,
) -> Optional[Dict[str, Any]]:
    """Pick next job dict from a list respecting FAST preference / live skip."""
    jobs = list(pending)
    if not jobs:
        return None
    ranked: List[Dict[str, Any]] = []
    for j in jobs:
        cls = job_class(j)
        if skip_live and cls == LIVE:
            continue
        ranked.append(j)
    if not ranked:
        return None
    if prefer_fast:
        fast = [j for j in ranked if job_class(j) == FAST]
        if fast:
            return fast[0]
    return ranked[0]
