"""Curriculum — failure-driven, holdout-safe, promote only on verified wins."""

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
SCRATCH_PATH = CUR_DIR / "scratch_tier.json"
HOLDOUT_PATH = ROOT / "memory" / "quizzes" / "holdout_ids.json"
HIDDEN_IDS_PATH = ROOT / "memory" / "quizzes" / "hidden_ids.json"
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


def _blocked_ids() -> Set[str]:
    ids: Set[str] = set()
    for path in (HOLDOUT_PATH, HIDDEN_IDS_PATH):
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            ids |= set(data.get("ids") or [])
        except Exception:
            pass
    # always block hidden_humaneval ids by prefix
    ids |= {f"he{str(i).zfill(2)}" for i in range(1, 11)}
    return ids


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
    state = _load_state()
    events = []
    for r in _tail_jsonl(PASS_PATH, 40):
        # only count verified-ish passes if confidence high and conf not soft-capped toys
        conf = float(r.get("confidence") or 0)
        events.append((r.get("timestamp") or "", True, conf))
    for r in _tail_jsonl(FAIL_PATH, 40):
        events.append((r.get("timestamp") or "", False, 0.0))
    events.sort(key=lambda x: x[0])
    if not events:
        return state

    wins = losses = 0
    last_ok = events[-1][1]
    for _, ok, conf in reversed(events):
        if ok != last_ok:
            break
        if ok:
            # ban promote-on-exit-zero soft conf: need conf >= 0.85 for win streak
            if conf >= 0.85:
                wins += 1
            else:
                break
        else:
            losses += 1

    promote_after = int(os.getenv("ETHER_CURRICULUM_PROMOTE_AFTER", "3"))
    demote_after = int(os.getenv("ETHER_CURRICULUM_DEMOTE_AFTER", "3"))
    tiers = load_tiers()
    tier = int(state.get("tier") or 0)

    if last_ok and wins >= promote_after and tier < max(0, len(tiers) - 1):
        tier = min(len(tiers) - 1, tier + 1)
        wins = 0
        losses = 0
        state["last_event"] = f"synced_promoted_to_{tier}"
    elif (not last_ok) and losses >= demote_after and tier > 0:
        tier = max(0, tier - 1)
        losses = 0
        wins = 0
        state["last_event"] = f"synced_demoted_to_{tier}"

    state["tier"] = tier
    state["wins"] = wins if last_ok else 0
    state["losses"] = losses if not last_ok else 0
    state["synced"] = True
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
    if SCRATCH_PATH.exists() and tiers:
        try:
            sc = json.loads(SCRATCH_PATH.read_text(encoding="utf-8"))
            extra = list(sc.get("tasks") or [])
            if extra:
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
    rate = float(os.getenv("ETHER_CURRICULUM_FAIL_RATE", "0.4"))
    if random.random() > rate:
        return None
    fails = _tail_jsonl(FAIL_PATH, 30)
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
            f"Write complete executable Python only with asserts.\n{obj}"
        ),
        "source": "failure_vault",
    }


def sample_objective() -> Dict[str, Any]:
    try:
        sync_from_vault()
    except Exception:
        pass

    blocked = _blocked_ids()
    driven = _failure_driven_objective()
    if driven and driven.get("id") not in blocked:
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
                "assert is_even(4) and not is_even(5)\n"
                "print(is_even(4))\n"
            ),
        }
    idx = current_tier_index()
    tier = tiers[idx]
    tasks = [t for t in (tier.get("tasks") or []) if (t.get("id") or "") not in blocked]
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


def record_outcome(
    success: bool,
    task_id: str = "",
    verification_score: float = 0.0,
    total_tests: int = 0,
) -> Dict[str, Any]:
    """Promote only on verified success (tests + verification_score)."""
    state = _load_state()
    tiers = load_tiers()
    promote_after = int(os.getenv("ETHER_CURRICULUM_PROMOTE_AFTER", "3"))
    demote_after = int(os.getenv("ETHER_CURRICULUM_DEMOTE_AFTER", "3"))

    verified = success and total_tests > 0 and float(verification_score) >= 0.7

    if verified:
        state["wins"] = int(state.get("wins") or 0) + 1
        state["losses"] = 0
    elif success and not verified:
        # soft success does not advance tier
        state["soft_wins"] = int(state.get("soft_wins") or 0) + 1
    else:
        state["losses"] = int(state.get("losses") or 0) + 1
        state["wins"] = 0

    hist = list(state.get("history") or [])
    hist.append(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "success": success,
            "verified": verified,
            "task_id": task_id,
            "tier": state.get("tier", 0),
            "verification_score": verification_score,
            "total_tests": total_tests,
        }
    )
    state["history"] = hist[-200:]

    tier = int(state.get("tier") or 0)
    if verified and int(state.get("wins") or 0) >= promote_after and tier < max(0, len(tiers) - 1):
        state["tier"] = tier + 1
        state["wins"] = 0
        state["losses"] = 0
        state["last_event"] = f"promoted_to_{state['tier']}_verified"
    elif (not success) and int(state.get("losses") or 0) >= demote_after and tier > 0:
        state["tier"] = tier - 1
        state["wins"] = 0
        state["losses"] = 0
        state["last_event"] = f"demoted_to_{state['tier']}"

    _save_state(state)
    return state
