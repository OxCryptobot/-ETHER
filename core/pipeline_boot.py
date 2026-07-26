"""Boot helpers applied at start of each Pipeline.run (bandit context)."""

from __future__ import annotations

from typing import Any, Dict


def select_strategy(policy: Any, objective: str) -> str:
    from core.learning import learning_enabled
    from core.pipeline_hooks import bandit_context

    if not learning_enabled():
        return "default"
    tier = 0
    try:
        from core.curriculum import current_tier_index

        tier = current_tier_index()
    except Exception:
        pass
    ctx = bandit_context(objective, tier=tier)
    try:
        return policy.select(ctx)
    except TypeError:
        return policy.select()


def prep_generated(code: str, objective: str) -> tuple[str, Dict[str, Any]]:
    from core.pipeline_hooks import prepare_code_for_sandbox

    return prepare_code_for_sandbox(code, objective)
