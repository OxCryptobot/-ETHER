"""Host-side auto rate-climb under training wheels.

2026-08-28: STOP easy-farm padding. Once eligible n>=40 the remaining
gap is not cured by more greeter copies. Foreman must not enqueue
auto_rc just because rate < 0.99.

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
COOLDOWN_S = int(os.getenv("ETHER_RATE_CLIMB_COOLDOWN_S", "30"))
WAVE_N = int(os.getenv("ETHER_RATE_CLIMB_WAVE_N", "2"))
FARM_N_CAP = int(os.getenv("ETHER_RATE_CLIMB_MAX_N", "40"))
FIXTURES = ("greeter", "wallet")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _wheels_on() -> bool:
    return (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0"


def _gate() -> Dict[str, Any]:
    if not PHASE1_GATE.exists():
        return {}
    try:
        return json.loads(PHASE1_GATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_honest_rate() -> Optional[float]:
    try:
        v = _gate().get("honest_rate_eligible")
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
    if write_job is None:
        return None
    if not _wheels_on():
        state["rate_climb_status"] = "skip_wheels_off"
        return None
    gate = _gate()
    rate = None
    try:
        if gate.get("honest_rate_eligible") is not None:
            rate = float(gate["honest_rate_eligible"])
    except Exception:
        rate = None
    if rate is None:
        state["rate_climb_status"] = "skip_no_rate"
        return None
    if rate >= TARGET:
        state["rate_climb_status"] = f"skip_rate_ok={rate:.4f}"
        return None
    n_e = int(gate.get("live_eligible_n") or 0)
    if n_e >= FARM_N_CAP:
        state["rate_climb_status"] = f"skip_farm_padding n={n_e} rate={rate:.4f}"
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
                f"(honest_rate={rate:.4f}<{TARGET} n={n_e}) under wheels"
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
                },
                {
                    "argv": [
                        ".venv/Scripts/python.exe",
                        "-m",
                        "core.atomic_rates",
                    ],
                    "timeout": 90,
                },
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
