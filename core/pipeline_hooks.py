"""Pipeline helpers — thin facades over pure strangler slices."""

from __future__ import annotations

from typing import Any, Dict, Iterator, Tuple

# Re-export pure prep API (backward compatible imports)
from core.pipeline_prep import (  # noqa: F401
    code_prep_disabled,
    no_code_prep,
    prepare_code_for_sandbox,
)


def bandit_context(objective: str, tier: int = 0, fail_kind: str = "") -> Dict[str, Any]:
    try:
        from core.multifile import is_multifile_objective

        multifile = is_multifile_objective(objective)
    except Exception:
        o = (objective or "").lower()
        multifile = any(
            k in o for k in ("class", "module", "refactor", "file", "package", "multi")
        )
    return {"tier": tier, "fail_kind": fail_kind, "multifile": multifile}


def apply_repo_oracle_gate(
    generated: str,
    objective: str,
    *,
    execution_score: float,
    verification_score: float,
    confidence: float,
) -> dict:
    """Delegate to pure core.pipeline_oracle (strangler)."""
    from core.pipeline_oracle import apply_repo_oracle_gate as _pure

    return _pure(
        generated,
        objective,
        execution_score=execution_score,
        verification_score=verification_score,
        confidence=confidence,
    )
