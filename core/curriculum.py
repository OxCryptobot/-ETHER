"""Curriculum sampler — graded coding tasks for autonomous improvement."""

from __future__ import annotations

import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
CUR_DIR = ROOT / "memory" / "curriculum"
STATE_PATH = CUR_DIR / "state.json"
MINED_PATH = CUR_DIR / "mined_tasks.json"


def curriculum_enabled() -> bool:
    return os.getenv("ETHER_CURRICULUM", "1") == "1"


def _load_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {"tier": 0, "wins": 0, "losses": 0, "history": []}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"tier": 0, "wins": 0, "losses": 0, "history": []}


def _save_state(state: Dict[str, Any]) -> None:
    CUR_DIR.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def load_tiers() -> List[Dict[str, Any]]:
    path = CUR_DIR / "tiers.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    tiers = list(data.get("tiers") or [])
    # blend mined tasks into highest tier for variety
    if MINED_PATH.exists():
        try:
            mined = json.loads(MINED_PATH.read_text(encoding="utf-8")).get("tasks") or []
            if mined and tiers:
                extra = [
                    {"id": t.get("id"), "title": t.get("title"), "objective": t.get("objective")}
                    for t in mined[:15]
                    if t.get("objective")
                ]
                tiers[-1].setdefault("tasks", []).extend(extra)
        except Exception:
            pass
    return tiers


def current_tier_index() -> int:
    state = _load_state()
    tiers = load_tiers()
    t = int(state.get("tier") or 0)
    return max(0, min(t, max(0, len(tiers) - 1)))


def sample_objective() -> Dict[str, Any]:
    tiers = load_tiers()
    if not tiers:
        return {
            "id": "fallback_even",
            "tier": 0,
            "title": "fallback",
            "objective": (
                "Write only this Python code with no markdown:\n"
                "def is_even(n):\n    return n % 2 == 0\n"
                "print(is_even(4))\nprint(is_even(5))\n"
            ),
        }
    idx = current_tier_index()
    tier = tiers[idx]
    tasks = list(tier.get("tasks") or [])
    if not tasks:
        tasks = [{"id": "empty", "title": "empty", "objective": "print(1)"}]
    task = random.choice(tasks)
    return {
        "id": task.get("id") or f"t{idx}",
        "tier": idx,
        "tier_name": tier.get("name") or f"tier_{idx}",
        "title": task.get("title") or task.get("id") or "task",
        "objective": task.get("objective") or "print(1)",
    }


def record_outcome(success: bool, task_id: str = "") -> Dict[str, Any]:
    state = _load_state()
    tiers = load_tiers()
    promote_after = int(os.getenv("ETHER_CURRICULUM_PROMOTE_AFTER", "5"))
    demote_after = int(os.getenv("ETHER_CURRICULUM_DEMOTE_AFTER", "4"))

    if success:
        state["wins"] = int(state.get("wins") or 0) + 1
        state["losses"] = 0
    else:
        state["losses"] = int(state.get("losses") or 0) + 1
        state["wins"] = 0

    hist = list(state.get("history") or [])
    hist.append(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "success": success,
            "task_id": task_id,
            "tier": state.get("tier", 0),
        }
    )
    state["history"] = hist[-200:]

    tier = int(state.get("tier") or 0)
    if success and int(state["wins"]) >= promote_after and tier < max(0, len(tiers) - 1):
        state["tier"] = tier + 1
        state["wins"] = 0
        state["losses"] = 0
        state["last_event"] = f"promoted_to_{state['tier']}"
    elif (not success) and int(state["losses"]) >= demote_after and tier > 0:
        state["tier"] = tier - 1
        state["wins"] = 0
        state["losses"] = 0
        state["last_event"] = f"demoted_to_{state['tier']}"

    _save_state(state)
    return state
