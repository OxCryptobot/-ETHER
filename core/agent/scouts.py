"""Batch 10 item 5e: goal-flow scouts (ETHER_GOAL_SCOUTS=1, default off). No model calls.

SWARM_DESIGN option 6: the outage that idled the 1650 was a queue problem, not a model problem.
Scouts keep the real queue flowing and ordered, using only pytest / SBFL / ruff on the CPU:

  rank    interleave() orders the ranked real goals by source in a weighted round robin
          (ETHER_SCOUT_PATTERN, default test_import x2, sbfl, import_error, test_import_assign, lint).
          test_import first (the only source with keeps live: 2/87 vs sbfl 0/133), but every cycle
          also gives SBFL and the rest a slot, so the best source is not drained before the others
          are touched (the finite-pool failure of a pure "prefer test_import" rule). Within a
          source the batch 3 rank (tractability, own and shared tries) is kept.
  refill  refill() runs one more failing-test shard (failures -> test_import / import_error /
          sbfl goals) plus lint goals when fewer than ETHER_SCOUT_MIN_SELECTABLE goals are
          selectable, at most every ETHER_SCOUT_EVERY_S. Planted goals are not a scout source:
          sota only plants when real selectable is 0 (item 5f).
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_PATTERN = "test_import,test_import,sbfl,import_error,test_import_assign,lint"


def enabled() -> bool:
    return os.getenv("ETHER_GOAL_SCOUTS", "0") == "1"


def pattern() -> List[str]:
    raw = os.getenv("ETHER_SCOUT_PATTERN", DEFAULT_PATTERN)
    out = [p.strip() for p in raw.split(",") if p.strip()]
    return out or DEFAULT_PATTERN.split(",")


def source(g: Dict[str, Any]) -> str:
    if g.get("kind") == "lint":
        return "lint"
    return str(g.get("via") or g.get("kind") or "other")


def interleave(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Weighted round robin over sources, order inside a source unchanged. Same set of goals."""
    groups: Dict[str, List[Dict[str, Any]]] = {}
    order: List[str] = []
    for g in rows:
        s = source(g)
        if s not in groups:
            groups[s] = []
            order.append(s)
        groups[s].append(g)
    pat = pattern()
    extra = [s for s in order if s not in pat]  # unlisted sources get one slot per cycle, after the pattern
    cycle = pat + extra
    out: List[Dict[str, Any]] = []
    while any(groups.values()):
        for s in cycle:
            if groups.get(s):
                out.append(groups[s].pop(0))
    return out


def _int(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def refill(root: Path, now: float | None = None) -> Dict[str, Any]:
    """One CPU-only refill pass when the selectable real queue is low. Never calls the model."""
    from core.agent import goal_source as gs

    root = Path(root)
    now = time.time() if now is None else now
    before = gs.why_blocked(root).get("selectable", 0)
    low = _int("ETHER_SCOUT_MIN_SELECTABLE", 3)
    if before >= low:
        return {"ran": False, "selectable": before, "why": "enough"}
    data = gs.load_index(root)
    last = data.get("scout_ts")
    try:
        last_s = datetime.fromisoformat(str(last)).timestamp() if last else None
    except ValueError:
        last_s = None
    if last_s is not None and now - last_s < _int("ETHER_SCOUT_EVERY_S", 600):
        return {"ran": False, "selectable": before, "why": "cooldown"}
    data["scout_ts"] = datetime.fromtimestamp(now, timezone.utc).isoformat()
    gs.save_index(root, data)
    row: Dict[str, Any] = {"ran": True, "selectable_before": before}
    try:
        scan = gs.scan(root, n_files=_int("ETHER_SCOUT_FILES", 16))
        row["scan"] = {k: scan.get(k) for k in ("files", "failing", "added", "goals", "secs")}
    except Exception as exc:
        row["scan_error"] = type(exc).__name__
    try:
        data = gs.load_index(root)
        n = 0
        for goal in gs.lint_goals(root):
            if goal["id"] not in data["done"] and goal["id"] not in data["goals"]:
                goal["tractability"] = gs.tractability(root, goal)
                data["goals"][goal["id"]] = goal
                n += 1
        data["lint_ts"] = gs._now()
        gs.save_index(root, data)
        row["lint_added"] = n
    except Exception as exc:
        row["lint_error"] = type(exc).__name__
    row["selectable"] = gs.why_blocked(root).get("selectable", 0)
    return row
