"""Preference learning from measured scoreboards.

Converts honest batch results into:
  1. Preference pairs written into the experience vault (offline RL signal)
  2. Live strategy win-rate stats that influence strategy_boost()

Doctrine: only real measured outcomes. No theatre. train_gates still gate storage.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
STATS_PATH = ROOT / "memory" / "experience" / "strategy_stats.json"
PREF_PATH = ROOT / "memory" / "experience" / "preferences.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_strategy_stats() -> Dict[str, Any]:
    if not STATS_PATH.exists():
        return {"strategies": {}, "updated": None, "n_episodes": 0}
    try:
        return json.loads(STATS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"strategies": {}, "updated": None, "n_episodes": 0}


def save_strategy_stats(stats: Dict[str, Any]) -> None:
    STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    stats["updated"] = _now()
    STATS_PATH.write_text(json.dumps(stats, indent=2), encoding="utf-8")


def live_strategy_boost(strategy: str) -> float:
    """Dynamic boost from measured win rates. Falls back to static TRUST."""
    try:
        from core.train_gates import STRATEGY_TRUST
    except Exception:
        STRATEGY_TRUST = {"tool_runtime": 3.0, "default": 1.0}

    base = float(STRATEGY_TRUST.get((strategy or "").strip(), 1.0))
    stats = load_strategy_stats()
    s = stats.get("strategies", {}).get((strategy or "").strip())
    if not s or s.get("n", 0) < 3:
        return base  # not enough data yet

    # Empirical success rate, tempered so it cannot explode
    rate = float(s.get("wins", 0)) / max(1, float(s.get("n", 1)))
    # Blend: 60% static doctrine, 40% measured (conservative while young)
    return 0.6 * base + 0.4 * (0.5 + rate) * base


def _update_stats_from_rows(rows: List[Dict[str, Any]]) -> None:
    stats = load_strategy_stats()
    strategies = stats.setdefault("strategies", {})
    for r in rows:
        strat = (r.get("strategy") or r.get("arm") or "unknown").strip()
        if not strat:
            continue
        entry = strategies.setdefault(strat, {"n": 0, "wins": 0, "score_sum": 0.0})
        entry["n"] += 1
        entry["score_sum"] += float(r.get("score") or 0.0)
        if r.get("ok") is True or float(r.get("score") or 0) >= 0.99:
            entry["wins"] += 1
    stats["n_episodes"] = int(stats.get("n_episodes") or 0) + 1
    save_strategy_stats(stats)


def record_preferences_from_scoreboard(
    scoreboard_path: str | Path,
    min_score_gap: float = 0.15,
) -> Dict[str, Any]:
    """Read a phase scoreboard and emit preference pairs + update live stats.

    Preference: higher score (or success) is preferred over lower.
    Only writes when there is a real measured difference.
    """
    path = Path(scoreboard_path)
    meta: Dict[str, Any] = {"stored": 0, "stats_updated": False, "reason": ""}
    if not path.exists():
        meta["reason"] = "missing_scoreboard"
        return meta

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        meta["reason"] = f"parse_error:{e}"
        return meta

    rows: List[Dict[str, Any]] = data.get("results") or []
    if not rows:
        meta["reason"] = "empty_results"
        return meta

    # Always update live strategy stats from measured rows
    _update_stats_from_rows(rows)
    meta["stats_updated"] = True

    # Form simple preferences: success > failure, higher score > lower
    successes = [r for r in rows if r.get("ok") is True or float(r.get("score") or 0) >= 0.99]
    failures = [r for r in rows if not (r.get("ok") is True or float(r.get("score") or 0) >= 0.99)]

    PREF_PATH.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with PREF_PATH.open("a", encoding="utf-8") as f:
        for s in successes:
            for fail in failures:
                gap = float(s.get("score") or 0) - float(fail.get("score") or 0)
                if gap < min_score_gap and s.get("ok") is not True:
                    continue
                pref = {
                    "timestamp": _now(),
                    "preferred": {
                        "mutation": s.get("mutation"),
                        "strategy": s.get("strategy") or s.get("arm"),
                        "score": s.get("score"),
                        "ok": s.get("ok"),
                    },
                    "rejected": {
                        "mutation": fail.get("mutation"),
                        "strategy": fail.get("strategy") or fail.get("arm"),
                        "score": fail.get("score"),
                        "ok": fail.get("ok"),
                        "reason": fail.get("reason") or fail.get("error"),
                    },
                    "gap": round(gap, 4),
                    "source": str(path.name),
                    "train_doctrine": "grok_v1",
                }
                f.write(json.dumps(pref) + "\n")
                n += 1

    meta["stored"] = n
    meta["reason"] = "ok"
    return meta


def preference_summary() -> Dict[str, Any]:
    stats = load_strategy_stats()
    n_pref = 0
    if PREF_PATH.exists():
        try:
            n_pref = sum(1 for _ in PREF_PATH.open(encoding="utf-8") if _.strip())
        except Exception:
            pass
    return {
        "n_preferences": n_pref,
        "n_episodes": stats.get("n_episodes", 0),
        "strategies": stats.get("strategies", {}),
        "updated": stats.get("updated"),
    }
