"""Host-side auto rate-climb under training wheels.

Skills (batchphase / keep-pushing) only guide Grok in chat. They do NOT
run on the Windows host. This module is what actually enqueues when:

  - pending is empty
  - honest_rate_eligible < target (default 0.99)
  - training wheels ON
  - cooldown elapsed

Called from scripts.foreman.enqueue_next after curriculum is exhausted.
Never lifts wheels. Never enqueues denylisted hard LIVE fixtures.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
PENDING = ROOT / "artifacts" / "jobs" / "pending"
PHASE1_GATE = ROOT / "artifacts" / "phase1_gate.json"

TARGET = float(os.getenv("ETHER_RATE_CLIMB_TARGET", "0.99"))
# 2026-08-28: tighter loop — 3 weeks of idle gaps was the real delay, not job wall time.
COOLDOWN_S = int(os.getenv("ETHER_RATE_CLIMB_COOLDOWN_S", "30"))
WAVE_N = int(os.getenv("ETHER_RATE_CLIMB_WAVE_N", "4"))
FIXTURES = ("greeter", "wallet")  # easy only; denylist hard stays out


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _wheels_on() -> bool:
    return (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0"


def read_honest_rate() -> Optional[float]:
    if not PHASE1_GATE.exists():
        return None
    try:
        data = json.loads(PHASE1_GATE.read_text(encoding="utf-8"))
        v = data.get("honest_rate_eligible")
        return float(v) if v is not None else None
    except Exception:
        return None


def _cooldown_ok(state: Dict[str, Any]) -> bool:
    ts = state.get("last_rate_climb_ts")
    if not ts:
        return True
    try:
        last = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - last).total_seconds() >= COOLDOWN_S
    except Exception:
        return True


def maybe_enqueue(
    state: Dict[str, Any],
    *,
    pending: Optional[Set[str]] = None,
    write_job=None,
) -> Optional[str]:
    """Enqueue up to WAVE_N easy gate_sample jobs if rate lags.

    write_job: callable(job_dict) -> Path from foreman.write_job
    Returns last job id or None.
    """
    if write_job is None:
        return None
    if not _wheels_on():
        state["rate_climb_status"] = "skip_wheels_off"
        return None
    rate = read_honest_rate()
    if rate is None:
        state["rate_climb_status"] = "skip_no_rate"
        return None
    if rate >= TARGET:
        state["rate_climb_status"] = f"skip_rate_ok={rate:.4f}"
        return None
    if pending is None:
        PENDING.mkdir(parents=True, exist_ok=True)
        pending = {
            p.stem
            for p in PENDING.glob("*.json")
            if p.name != ".gitkeep"
        }
    if len(pending) > 0:
        state["rate_climb_status"] = "skip_pending_nonempty"
        return None
    if not _cooldown_ok(state):
        state["rate_climb_status"] = "skip_cooldown"
        return None
    try:
        from core.queue_governor import may_enqueue

        if not may_enqueue():
            state["rate_climb_status"] = "skip_governor"
            return None
    except Exception:
        pass

    stamp = datetime.now(timezone.utc).strftime("%H%M%S")
    idx = int(state.get("rate_climb_idx") or 0)
    enqueued: List[str] = []
    for i in range(WAVE_N):
        fixture = FIXTURES[(idx + i) % len(FIXTURES)]
        jid = f"auto_rc_{fixture}_{stamp}_{i}"
        if jid in pending or jid in enqueued:
            continue
        job = {
            "id": jid,
            "class": "gate_sample",
            "note": (
                f"AUTO rate-climb gate_sample {fixture} "
                f"(honest_rate={rate:.4f}<{TARGET}) under wheels — host autonomy"
            ),
            "continue_on_fail": True,
            "source": "foreman_rate_climb",
            "created": _now(),
            "steps": [
                {
                    "argv": [
                        ".venv/Scripts/python.exe",
                        "-m",
                        "scripts.batch_phase_d",
                        "--arm",
                        "direct",
                        "--mode",
                        "live",
                        "--fixture",
                        fixture,
                        "--max-steps",
                        "10",
                        "--timeout",
                        "200",
                        "--scoreboard",
                        f"artifacts/scoreboard_{jid}.json",
                    ],
                    "timeout": 300,
                }
            ],
        }
        write_job(job)
        enqueued.append(jid)

    if enqueued:
        state["rate_climb_idx"] = idx + len(enqueued)
        state["last_rate_climb_ts"] = _now()
        state["last_enqueued"] = enqueued[-1]
        state["mode"] = "rate_climb"
        state["rate_climb_status"] = f"enqueued={enqueued} rate={rate:.4f}"
        return enqueued[-1]

    state["rate_climb_status"] = "noop"
    return None
