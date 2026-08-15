"""Job class contract — FAST vs LIVE + MEASURE/RECOVERY buckets (P2 + critical 8).

Host prefers MEASURE > RECOVERY > FAST > LIVE.
Jobs may set "class": "fast" | "live" | "any" | "measure" | "recovery".
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

FAST = "fast"
LIVE = "live"
ANY = "any"
MEASURE = "measure"
RECOVERY = "recovery"


def normalize_class(raw: Any) -> str:
    s = str(raw or ANY).strip().lower()
    if s in (MEASURE, "honest", "snapshot", "kpi"):
        return MEASURE
    if s in (RECOVERY, "playbook", "critique", "labradorite"):
        return RECOVERY
    if s in (FAST, "scripted", "gate", "pytest"):
        return FAST
    if s in (LIVE, "pipeline_live", "llm"):
        return LIVE
    return ANY


def job_class(job: Dict[str, Any]) -> str:
    if "class" in job:
        cls = normalize_class(job.get("class"))
        if cls != ANY:
            return cls
    note = str(job.get("note") or "").lower()
    jid = str(job.get("id") or "").lower()
    src = str(job.get("source") or "").lower()
    hay = f"{note} {jid} {src}"
    if any(x in hay for x in ("measure", "honest_live", "soft_launch", "phase3_snapshot", "lora_dry", "honest_kpi")):
        return MEASURE
    if any(x in hay for x in ("playbook:", "critique_hyp", "labradorite", "diag_after")):
        return RECOVERY
    if any(x in hay for x in ("live", "pipeline_ledger", "ss_pipeline_ledger")) and "scripted" not in hay:
        return LIVE
    if any(x in hay for x in ("scripted", "pytest", "ruff", "pep8", "whats_next", "archive", "train_gates")):
        return FAST
    return ANY


def schedule_rank(job: Dict[str, Any]) -> tuple:
    """Lower tuple sorts first."""
    cls = job_class(job)
    order = {MEASURE: 0, RECOVERY: 1, FAST: 2, ANY: 3, LIVE: 4}
    return (order.get(cls, 3), str(job.get("id") or ""))


def pick_next(
    pending: Iterable[Dict[str, Any]],
    *,
    prefer_fast: bool = False,
    skip_live: bool = False,
) -> Optional[Dict[str, Any]]:
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
    ranked.sort(key=schedule_rank)
    if prefer_fast:
        non_live = [j for j in ranked if job_class(j) != LIVE]
        if non_live:
            return non_live[0]
    return ranked[0]
