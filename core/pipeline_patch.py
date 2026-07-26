"""Monkey-friendly helpers applied at start of Pipeline.run without rewriting entire pipeline."""

from __future__ import annotations

from typing import Any, Dict

from core.pipeline_hooks import bandit_context, prepare_code_for_sandbox


def select_strategy(policy: Any, objective: str) -> str:
    tier = 0
    try:
        from core.curriculum import current_tier_index

        tier = current_tier_index()
    except Exception:
        pass
    ctx = bandit_context(objective, tier=tier)
    try:
        return policy.select(context=ctx)
    except TypeError:
        return policy.select()


def prep_code(code: str, objective: str) -> tuple[str, Dict[str, Any]]:
    return prepare_code_for_sandbox(code, objective)
