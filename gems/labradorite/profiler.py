"""Labradorite — simple performance critique."""

from __future__ import annotations

from typing import List

from core.schemas import (
    Envelope,
    ResponseEnvelope,
    GemError,
    GemErrorType,
    LabradoriteRequest,
    LabradoriteResponse,
)


class Labradorite:
    """Lightweight static critique."""

    def execute(self, request: Envelope) -> ResponseEnvelope:
        try:
            if isinstance(request.payload, LabradoriteRequest):
                code = request.payload.code
            else:
                data = request.payload.model_dump() if hasattr(request.payload, "model_dump") else {}
                code = data.get("code", "")

            lines = code.count("\n") + 1
            complexity = min(1.0, lines / 200)

            suggestions: List[str] = []
            if "for " in code and "range(" in code:
                suggestions.append("Consider list comprehensions or vectorized operations")
            if code.count("if ") > 8:
                suggestions.append("High number of conditionals — consider refactoring")

            critique = f"Approximately {lines} lines. Complexity score: {complexity:.2f}"

            payload = LabradoriteResponse(
                complexity_score=round(complexity, 2),
                critique=critique,
                suggested_improvements=suggestions,
                confidence_score=0.55,
            )

            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="labradorite",
                payload=payload,
            )
        except Exception as e:
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="labradorite",
                error=GemError(type=GemErrorType.RUNTIME, message=str(e), recoverable=True),
            )
