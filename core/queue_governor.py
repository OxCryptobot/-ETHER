"""Queue depth governor — prevent STEADY self-DDoS + time-based pause."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
PENDING = ROOT / "artifacts" / "jobs" / "pending"
STATE_PATH = ROOT / "artifacts" / "queue_governor_state.json"

MAX_PENDING = int(os.getenv("ETHER_MAX_PENDING", "6"))
STEADY_PAUSE_AT = int(os.getenv("ETHER_STEADY_PAUSE_AT", "4"))
STEADY_RESUME_AT = int(os.getenv("ETHER_STEADY_RESUME_AT", "2"))
MAX_ENQUEUE_PER_TICK = int(os.getenv("ETHER_MAX_ENQUEUE_PER_TICK", "2"))
# Moonshot 16: if pending > HIGH for > HOLD_S, pause until resume
HIGH_DEPTH = int(os.getenv("ETHER_QUEUE_HIGH_DEPTH", "8"))
HIGH_HOLD_S = float(os.getenv("ETHER_QUEUE_HIGH_HOLD_S", "120"))


def pending_count() -> int:
    PENDING.mkdir(parents=True, exist_ok=True)
    return sum(1 for p in PENDING.glob("*.json") if p.name != ".gitkeep")


def _load_state() -> Dict[str, Any]:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_state(data: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _update_high_watermark(depth: int) -> bool:
    """Return True if STEADY should pause due to sustained high depth."""
    st = _load_state()
    now = time.time()
    if depth > HIGH_DEPTH:
        since = float(st.get("high_since") or now)
        if "high_since" not in st:
            st["high_since"] = now
            since = now
        st["last_depth"] = depth
        _save_state(st)
        return (now - since) >= HIGH_HOLD_S
    # recovered
    if "high_since" in st:
        st.pop("high_since", None)
        st["last_depth"] = depth
        _save_state(st)
    return False


def may_enqueue(n_already: int = 0) -> bool:
    return pending_count() + n_already < MAX_PENDING


def may_enqueue_steady(state: Dict[str, Any] | None = None) -> bool:
    # Moonshot 24: microbench freeze
    try:
        from core.microbench import is_steady_frozen

        if is_steady_frozen():
            return False
    except Exception:
        pass
    depth = pending_count()
    if _update_high_watermark(depth):
        # sustained high — only resume when below STEADY_RESUME_AT
        if depth > STEADY_RESUME_AT:
            return False
    if depth >= STEADY_PAUSE_AT:
        return False
    if depth >= MAX_PENDING:
        return False
    return True


def max_enqueue_this_tick() -> int:
    room = max(0, MAX_PENDING - pending_count())
    return min(MAX_ENQUEUE_PER_TICK, room)


def classify_bucket(job: Dict[str, Any]) -> str:
    jid = str(job.get("id") or "").lower()
    note = str(job.get("note") or "").lower()
    src = str(job.get("source") or "").lower()
    hay = f"{jid} {note} {src}"
    if any(x in hay for x in ("measure", "honest_live", "soft_launch", "phase3_snapshot", "lora_dry")):
        return "measure"
    if any(x in hay for x in ("playbook:", "critique_hyp", "labradorite", "recovery", "diag_after", "zcr_")):
        return "recovery"
    if any(x in hay for x in ("live", "pipeline_ledger")) and "scripted" not in hay:
        return "live"
    return "fast"


def bucket_rank(bucket: str) -> int:
    order = {"measure": 0, "recovery": 1, "fast": 2, "live": 3}
    return order.get(bucket, 2)


def training_wheels_on() -> bool:
    return (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0"


def status_snapshot() -> Dict[str, Any]:
    depth = pending_count()
    return {
        "pending": depth,
        "max_pending": MAX_PENDING,
        "steady_pause_at": STEADY_PAUSE_AT,
        "steady_resume_at": STEADY_RESUME_AT,
        "high_depth": HIGH_DEPTH,
        "high_hold_s": HIGH_HOLD_S,
        "may_enqueue": may_enqueue(),
        "may_enqueue_steady": may_enqueue_steady(),
        "max_enqueue_this_tick": max_enqueue_this_tick(),
        "training_wheels": training_wheels_on(),
    }
