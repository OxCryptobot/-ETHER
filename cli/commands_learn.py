"""Learn-stats helper used by CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from core.learning import BanditPolicy


def learn_stats() -> Dict[str, Any]:
    policy = BanditPolicy()
    snap = policy.snapshot()
    streak_path = Path("memory/learning/fail_streak.json")
    streak = {}
    if streak_path.exists():
        try:
            streak = json.loads(streak_path.read_text(encoding="utf-8"))
        except Exception:
            streak = {}
    return {"bandit": snap, "fail_streak": streak}
