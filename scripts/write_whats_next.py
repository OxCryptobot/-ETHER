"""Write artifacts/whats_next.json — single source for UI/CLI "what's next".

  python -m scripts.write_whats_next
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "artifacts" / "whats_next.json"
PENDING = ROOT / "artifacts" / "jobs" / "pending"
STATUS = ROOT / "artifacts" / "host_agent_status.json"
LAST = ROOT / "artifacts" / "host_agent_last_job.json"


def _load(name: str) -> dict:
    p = ROOT / "artifacts" / name
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    pending = (
        sorted(p.stem for p in PENDING.glob("*.json") if p.name != ".gitkeep")
        if PENDING.exists()
        else []
    )
    host: dict = {}
    last: dict = {}
    try:
        if STATUS.exists():
            host = json.loads(STATUS.read_text(encoding="utf-8"))
        if LAST.exists():
            last = json.loads(LAST.read_text(encoding="utf-8"))
    except Exception:
        pass

    p1d = _load("phase1d_status.json")
    p1d_detail = (
        f"checks {p1d.get('checks_ok')}/{p1d.get('checks_n')} status={p1d.get('status')}; live OPEN under 4B"
        if p1d
        else "scripted GREEN; live OPEN under 4B; latency honesty + live_budget landed"
    )

    ps = _load("pipeline_strangler.json")
    pipe_note = (
        f"pipeline_god_file: {ps.get('status')} "
        f"bytes={ps.get('pipeline_bytes')} extracted={ps.get('extracted_ok')}/{ps.get('extracted_n')}"
        if ps
        else "pipeline_god_file: STRANGLER_ACTIVE (pure slices green; body still large)"
    )

    ctx = _load("context_budget.json")
    ctx_note = f"context:{ctx.get('grade') or ctx.get('status') or '—'} util={ctx.get('utilization')}"

    router = _load("model_router.json")
    lane_note = (
        f"lanes fast={router.get('fast_model')} live={router.get('live_model')}"
        if router
        else "lanes: default"
    )

    retire = _load("timeout_retirement.json")
    if not retire:
        try:
            from core.timeout_retirement import compute as retire_compute

            retire = retire_compute()
        except Exception:
            retire = {}
    acts = retire.get("actions") or []
    retire_note = (
        f"timeout_retire rate={retire.get('timeout_rate')} "
        f"action={(acts[0] if acts else '—')}"
    )

    phase_board = [
        {"id": "1A", "name": "Tool-first", "status": "COMPLETE"},
        {"id": "1B", "name": "AgentState", "status": "COMPLETE"},
        {"id": "1C", "name": "AST transactional", "status": "COMPLETE"},
        {
            "id": "1D",
            "name": "Measured lift",
            "status": "PARTIAL",
            "detail": p1d_detail,
        },
    ]

    blocked = [
        "soft_launch: blocked until live lift or explicit gate policy",
        pipe_note,
    ]
    if retire.get("timeout_rate") is not None and not retire.get("ok"):
        blocked.append(
            f"live_timeout_rate={retire.get('timeout_rate')} "
            f"(target < {retire.get('target_rate')})"
        )

    payload = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "next_job": pending[0] if pending else None,
        "queue_head": pending[:8],
        "queue_depth": len(pending),
        "host_phase": host.get("phase"),
        "last_job": last.get("job_id"),
        "last_ok": last.get("ok"),
        "last_failure_type": last.get("failure_type"),
        "phase_board": phase_board,
        "blocked": blocked,
        "signals": {
            "context": ctx_note,
            "model_router": lane_note,
            "timeout_retirement": retire_note,
            "adapter_default_off": ps.get("adapter_default_off") if ps else True,
        },
        "resolved": [
            "dashboard: single Control Matrix at http://127.0.0.1:8787/ only",
            "1D latency honesty + live_budget + critique→Plan wire",
            "pipeline pure slices: tool_first/score/terminal/adapter/oracle (flag OFF)",
            "timeout diagnosis + retirement plan + LIVE denylist",
            "model dual-lane router + context grades + microbench schedule",
        ],
        "operator": [
            "python -m scripts.ether_cli status",
            "python -m scripts.ether_cli next",
            "python -m scripts.ether_cli doctor",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
