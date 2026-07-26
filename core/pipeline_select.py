"""Strategy selection with curriculum context — import from pipeline."""

from __future__ import annotations

from typing import Any, Dict

from core.learning import BanditPolicy, learning_enabled
from core.pipeline_hooks import bandit_context


def select_strategy(objective: str, policy: BanditPolicy | None = None) -> str:
    if not learning_enabled():
        return "default"
    pol = policy or BanditPolicy()
    tier = 0
    try:
        from core.curriculum import current_tier_index

        tier = current_tier_index()
    except Exception:
        pass
    ctx: Dict[str, Any] = bandit_context(objective, tier=tier)
    return pol.select(context=ctx)
