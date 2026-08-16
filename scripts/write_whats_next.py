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

    p1d_detail = "scripted GREEN; live OPEN under 4B; latency honesty + live_budget landed"
    try:
        p1d = json.loads((ROOT / "artifacts" / "phase1d_status.json").read_text(encoding="utf-8"))
        p1d_detail = (
            f"checks {p1d.get('checks_ok')}/{p1d.get('checks_n')} "
            f"status={p1d.get('status')}; live OPEN under 4B"
        )
    except Exception:
        pass

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
        "pipeline_god_file: still open",
        # dual_dashboard RESOLVED — host-first Control Matrix is primary
    ]

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
        "resolved": [
            "dual_dashboard: host-first Control Matrix (/) — legacy at /legacy only",
            "1D latency honesty + live_budget + critique→Plan wire",
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
