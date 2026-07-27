"""Strategy selection with curriculum context.

Live path: called by ``Pipeline.run`` (core/pipeline.py). Everything here
exists so that ``BanditPolicy.select`` actually receives its context features.
``Pipeline.run`` used to call ``self.policy.select()`` with no argument, which
left ``multifile``/``fail_kind``/``tier`` permanently unset and silently
downgraded the contextual bandit to plain epsilon-greedy.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.learning import BanditPolicy, learning_enabled
from core.pipeline_hooks import bandit_context


def current_tier() -> int:
    """Curriculum tier, or 0 when the curriculum is unavailable."""
    try:
        from core.curriculum import current_tier_index

        return int(current_tier_index())
    except Exception:
        return 0


def select_strategy(
    objective: str,
    policy: Optional[BanditPolicy] = None,
    fail_kind: str = "",
) -> str:
    """Pick a generation strategy for `objective`.

    Returns "default" when learning is disabled, matching the behaviour the
    caller had inline before this was wired up.
    """
    if not learning_enabled():
        return "default"
    pol = policy if policy is not None else BanditPolicy()
    ctx: Dict[str, Any] = bandit_context(objective, tier=current_tier(), fail_kind=fail_kind)
    return pol.select(context=ctx)
