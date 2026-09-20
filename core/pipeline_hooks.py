"""Pipeline helpers — thin facades over pure strangler slices."""
from __future__ import annotations
from typing import Any, Dict
from core.pipeline_prep import (  # noqa: F401
    code_prep_disabled,
    no_code_prep,
    prepare_code_for_sandbox,
)
from core.pipeline_context import bandit_context  # noqa: F401

def apply_repo_oracle_gate(
    generated: str,
    objective: str,
    *,
    execution_score: float,
    verification_score: float,
    confidence: float,
) -> dict:
    from core.pipeline_oracle import apply_repo_oracle_gate as _pure
    return _pure(
        generated,
        objective,
        execution_score=execution_score,
        verification_score=verification_score,
        confidence=confidence,
    )

def finalize_coding(row: Dict[str, Any], *, path: str = "pipeline") -> Dict[str, Any]:
    from core.kernel.strangle import finalize
    return finalize(row, path=path)
