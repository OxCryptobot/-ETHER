"""Strategy selection with curriculum context."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

from core.learning import STRATEGY_BEHAVIOUR, BanditPolicy, learning_enabled
from core.pipeline_context import bandit_context


def current_tier() -> int:
    try:
        from core.curriculum import current_tier_index

        return int(current_tier_index())
    except Exception:
        return 0


def select_strategy_with_context(
    objective: str,
    policy: Optional[BanditPolicy] = None,
    fail_kind: str = "",
) -> Tuple[str, Dict[str, Any]]:
    """Pick a strategy and return the context it was picked in."""
    ctx: Dict[str, Any] = bandit_context(
        objective, tier=current_tier(), fail_kind=fail_kind
    )
    force = (os.getenv("ETHER_FORCE_STRATEGY") or "").strip()
    if force and force in STRATEGY_BEHAVIOUR:
        return force, ctx
    if not learning_enabled():
        return "default", ctx
    pol = policy if policy is not None else BanditPolicy()
    return pol.select(context=ctx), ctx


def select_strategy(
    objective: str,
    policy: Optional[BanditPolicy] = None,
    fail_kind: str = "",
) -> str:
    return select_strategy_with_context(objective, policy, fail_kind)[0]
