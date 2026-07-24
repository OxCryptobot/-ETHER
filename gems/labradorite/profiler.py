"""Labradorite — simple performance critique."""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field

from core.schemas import Envelope, ResponseEnvelope, GemError, GemErrorType


class LabradoriteRequest(BaseModel):
    code: str
    language: str = "python"
    baseline: Optional[str] = None


class LabradoriteResponse(BaseModel):
    complexity_score: float = 0.5
    critique: str = ""
    suggested_improvements: List[str] = Field(default_factory=list)
    confidence_score: float = 0.6


class Labradorite:
    """Lightweight static critique (full profiling later)."""

    def execute(self, request: Envelope) -> ResponseEnvelope:
        try:
            data = request.payload.model_dump() if hasattr(request.payload, "model_dump") else {}
            code = data.get("code", "")

            lines = code.count("\n") + 1
            complexity = min(1.0, lines / 200)

            suggestions = []
            if "for " in code and "range(" in code:
                suggestions.append("Consider list comprehensions or vectorized operations where possible")
            if code.count("if ") > 8:
                suggestions.append("High number of conditionals — consider refactoring")

            critique = f"Code has approximately {lines} lines. Estimated complexity score: {complexity:.2f}"

            payload = LabradoriteResponse(
                complexity_score=round(complexity, 2),
                critique=critique,
                suggested_improvements=suggestions,
                confidence_score=0.55,
            )

            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="labradorite",
                payload=payload,  # type: ignore
            )
        except Exception as e:
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="labradorite",
                error=GemError(type=GemErrorType.RUNTIME, message=str(e), recoverable=True),
            )
