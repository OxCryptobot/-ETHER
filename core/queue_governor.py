"""Queue depth governor — prevent STEADY self-DDoS.

Critical fix #1: hard max pending.
Critical fix #8: class buckets MEASURE > RECOVERY > FAST > LIVE.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
PENDING = ROOT / "artifacts" / "jobs" / "pending"

# Hard caps — never flood the queue
MAX_PENDING = int(os.getenv("ETHER_MAX_PENDING", "6"))
STEADY_PAUSE_AT = int(os.getenv("ETHER_STEADY_PAUSE_AT", "4"))
STEADY_RESUME_AT = int(os.getenv("ETHER_STEADY_RESUME_AT", "2"))
MAX_ENQUEUE_PER_TICK = int(os.getenv("ETHER_MAX_ENQUEUE_PER_TICK", "2"))


def pending_count() -> int:
    PENDING.mkdir(parents=True, exist_ok=True)
    return sum(1 for p in PENDING.glob("*.json") if p.name != ".gitkeep")


def may_enqueue(n_already: int = 0) -> bool:
    return pending_count() + n_already < MAX_PENDING


def may_enqueue_steady(state: Dict[str, Any] | None = None) -> bool:
    depth = pending_count()
    if depth >= STEADY_PAUSE_AT:
        return False
    if depth >= MAX_PENDING:
        return False
    return True


def max_enqueue_this_tick() -> int:
    room = max(0, MAX_PENDING - pending_count())
    return min(MAX_ENQUEUE_PER_TICK, room)


def classify_bucket(job: Dict[str, Any]) -> str:
    """MEASURE > RECOVERY > FAST > LIVE."""
    jid = str(job.get("id") or "").lower()
    note = str(job.get("note") or "").lower()
    src = str(job.get("source") or "").lower()
    hay = f"{jid} {note} {src}"
    if any(x in hay for x in ("measure", "honest_live", "soft_launch", "phase3_snapshot", "lora_dry")):
        return "measure"
    if any(x in hay for x in ("playbook:", "critique_hyp", "labradorite", "recovery", "diag_after")):
        return "recovery"
    if any(x in hay for x in ("live", "pipeline_ledger")) and "scripted" not in hay:
        return "live"
    return "fast"


def bucket_rank(bucket: str) -> int:
    order = {"measure": 0, "recovery": 1, "fast": 2, "live": 3}
    return order.get(bucket, 2)


def status_snapshot() -> Dict[str, Any]:
    return {
        "pending": pending_count(),
        "max_pending": MAX_PENDING,
        "steady_pause_at": STEADY_PAUSE_AT,
        "steady_resume_at": STEADY_RESUME_AT,
        "may_enqueue": may_enqueue(),
        "may_enqueue_steady": may_enqueue_steady(),
        "max_enqueue_this_tick": max_enqueue_this_tick(),
    }
