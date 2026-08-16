"""Moonshot 21 / Phase 1D — Critique → PlanState wire.

When Labradorite (or any critique) records a typed FAIL with hypothesis text,
feed PlanState.should_replan so the next experiment is smaller/different.
Does not enqueue LIVE. Does not lift training wheels.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "critique_plan_wire.json"
CRIT_DIR = ROOT / "artifacts" / "critiques"


def _load_critiques(limit: int = 30) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not CRIT_DIR.exists():
        return rows
    files = sorted(CRIT_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in files[:limit]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict):
            rows.append(data)
    return rows


def _failure_type(c: Dict[str, Any]) -> str:
    for k in ("failure_type", "type", "kind"):
        v = c.get(k)
        if v:
            return str(v).strip().lower()
    text = str(c.get("hypothesis") or c.get("note") or c.get("summary") or "").lower()
    for token in (
        "budget_exhaust",
        "timeout",
        "tool_runtime_failed_terminal",
        "max_steps",
        "no_progress",
        "live_fail",
        "parse_fail",
    ):
        if token in text:
            return token
    return "unknown"


def wire_latest(limit: int = 12) -> Dict[str, Any]:
    from core.plan_state import plan_from_failure

    critiques = _load_critiques(limit=limit)
    events: List[Dict[str, Any]] = []
    for c in critiques:
        ft = _failure_type(c)
        obj = str(c.get("job_id") or c.get("id") or c.get("note") or "critique")[:200]
        hyp_in = str(c.get("hypothesis") or c.get("summary") or "")[:300]
        plan = plan_from_failure(
            objective=obj,
            failure_type=ft,
            prior_confidence=0.5,
            training_wheels=True,
        )
        # Prefer critique's own hypothesis text when present
        if hyp_in and plan.get("replan"):
            plan["hypothesis"] = f"{plan.get('hypothesis')}; critique:{hyp_in[:160]}"
        events.append(
            {
                "job_id": c.get("job_id") or c.get("id"),
                "failure_type": ft,
                "replan": plan.get("replan"),
                "hypothesis": plan.get("hypothesis"),
                "confidence": plan.get("confidence"),
            }
        )

    replanned = sum(1 for e in events if e.get("replan"))
    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "n_critiques": len(critiques),
        "n_replanned": replanned,
        "events_tail": events[:8],
        "latest_hypothesis": (events[0]["hypothesis"] if events else None),
        "training_wheels": True,
        "note": "Critique FAIL → PlanState.replan. Never auto-lifts soft launch.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(wire_latest(), indent=2))
