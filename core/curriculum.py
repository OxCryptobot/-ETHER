"""Curriculum — graded tasks, vault sync, failure-driven sampling."""

from __future__ import annotations

import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

ROOT = Path(__file__).resolve().parents[1]
CUR_DIR = ROOT / "memory" / "curriculum"
STATE_PATH = CUR_DIR / "state.json"
MINED_PATH = CUR_DIR / "mined_tasks.json"
HOLDOUT_PATH = ROOT / "memory" / "quizzes" / "holdout_ids.json"
PASS_PATH = ROOT / "memory" / "experience" / "pass.jsonl"
FAIL_PATH = ROOT / "memory" / "experience" / "fail.jsonl"


def curriculum_enabled() -> bool:
    return os.getenv("ETHER_CURRICULUM", "1") == "1"


def _load_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {"tier": 0, "wins": 0, "losses": 0, "history": [], "synced": False}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"tier": 0, "wins": 0, "losses": 0, "history": [], "synced": False}


def _save_state(state: Dict[str, Any]) -> None:
    CUR_DIR.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _holdout_ids() -> Set[str]:
    if not HOLDOUT_PATH.exists():
        return set()
    try:
        data = json.loads(HOLDOUT_PATH.read_text(encoding="utf-8"))
        return set(data.get("ids") or [])
    except Exception:
        return set()


def _tail_jsonl(path: Path, n: int = 40) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[-n:]:
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        return []
    return rows


def sync_from_vault() -> Dict[str, Any]:
    """Rebuild consecutive wins/losses from recent vault so tier tracks reality."""
    state = _load_state()
    events = []
    for r in _tail_jsonl(PASS_PATH, 30):
        events.append((r.get("timestamp") or "", True))
    for r in _tail_jsonl(FAIL_PATH, 30):
        events.append((r.get("timestamp") or "", False))
    events.sort(key=lambda x: x[0])
    if not events:
        return state

    # consecutive streak from the end
    wins = losses = 0
    last = events[-1][1]
    for _, ok in reversed(events):
        if ok == last:
            if ok:
                wins += 1
            else:
                losses += 1
        else:
            break

    promote_after = int(os.getenv("ETHER_CURRICULUM_PROMOTE_AFTER", "3"))
    demote_after = int(os.getenv("ETHER_CURRICULUM_DEMOTE_AFTER", "3"))
    tiers = load_tiers()
    tier = int(state.get("tier") or 0)

    # apply promotions/demotions as if streak happened
    if last and wins >= promote_after and tier < max(0, len(tiers) - 1):
        # how many promote steps available from streak
        steps = wins // promote_after
        tier = min(len(tiers) - 1, tier + max(1, min(steps, 2)))
        wins = wins % promote_after
        losses = 0
        state["last_event"] = f"synced_promoted_to_{tier}"
    elif (not last) and losses >= demote_after and tier > 0:
        tier = max(0, tier - 1)
        losses = 0
        wins = 0
        state["last_event"] = f"synced_demoted_to_{tier}"

    state["tier"] = tier
    state["wins"] = wins if last else 0
    state["losses"] = losses if not last else 0
    state["synced"] = True
    state["vault_pass"] = len(_tail_jsonl(PASS_PATH, 500))
    state["vault_fail"] = len(_tail_jsonl(FAIL_PATH, 500))
    _save_state(state)
    return state


def load_tiers() -> List[Dict[str, Any]]:
    path = CUR_DIR / "tiers.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    tiers = list(data.get("tiers") or [])
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


def _failure_driven_objective() -> Optional[Dict[str, Any]]:
    """~40% of the time: practice from recent FAIL vault."""
    if random.random() > float(os.getenv("ETHER_CURRICULUM_FAIL_RATE", "0.4")):
        return None
    fails = _tail_jsonl(FAIL_PATH, 25)
    if not fails:
        return None
    f = random.choice(fails)
    obj = f.get("objective") or ""
    kind = f.get("fail_kind") or "runtime"
    if not obj:
        return None
    return {
        "id": f"repair_{f.get('task_id') or 'x'}",
        "tier": current_tier_index(),
        "tier_name": "failure_repair",
        "title": f"repair:{kind}",
        "objective": (
            f"Fix this previously failed task. Failure class was {kind}.\n"
            f"Write complete executable Python only.\n{obj}"
        ),
        "source": "failure_vault",
    }


def sample_objective() -> Dict[str, Any]:
    # keep tier honest vs vault
    try:
        sync_from_vault()
    except Exception:
        pass

    holdout = _holdout_ids()
    driven = _failure_driven_objective()
    if driven and driven.get("id") not in holdout:
        return driven

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
    tasks = [t for t in (tier.get("tasks") or []) if (t.get("id") or "") not in holdout]
    if not tasks:
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
        "source": "tier",
    }


def record_outcome(success: bool, task_id: str = "") -> Dict[str, Any]:
    state = _load_state()
    tiers = load_tiers()
    promote_after = int(os.getenv("ETHER_CURRICULUM_PROMOTE_AFTER", "3"))
    demote_after = int(os.getenv("ETHER_CURRICULUM_DEMOTE_AFTER", "3"))

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
