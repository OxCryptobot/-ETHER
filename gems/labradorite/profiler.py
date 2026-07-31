"""Labradorite — essential critique & review gem (infinity loop).

Not optional. Pipeline always runs Labradorite after Black Tourmaline so
Amethyst can log the review and the memory bus can feed the next Selenite plan.
"""

from __future__ import annotations

import re
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
    """Static + heuristic review that produces actionable loop signals."""

    def execute(self, request: Envelope) -> ResponseEnvelope:
        try:
            if isinstance(request.payload, LabradoriteRequest):
                code = request.payload.code or ""
            else:
                data = request.payload.model_dump() if hasattr(request.payload, "model_dump") else {}
                code = data.get("code", "") or ""

            lines = code.count("\n") + (1 if code else 0)
            complexity = min(1.0, lines / 200.0)
            suggestions: List[str] = []
            flags: List[str] = []

            if not code.strip():
                suggestions.append("No code to review — generation stage produced empty artifact")
                flags.append("empty")
            if "assert " not in code and "assert(" not in code:
                suggestions.append("Add asserts that prove correctness before user-facing delivery")
                flags.append("no_asserts")
            if re.search(r"\beval\s*\(|\bexec\s*\(|__import__\s*\(", code):
                suggestions.append("Remove dynamic eval/exec — Black Tourmaline will reject")
                flags.append("dynamic_exec")
            if code.count("if ") > 8:
                suggestions.append("High conditional density — consider table-driven or early-return structure")
                flags.append("branchy")
            if "for " in code and "range(" in code and "append(" in code:
                suggestions.append("Consider list comprehensions or generator expressions for clarity")
            if lines > 120:
                suggestions.append("Large artifact — prefer smaller pure functions for sandbox scoring")
                flags.append("large")
            if not re.search(r"^def\s+\w+", code, re.M) and "class " not in code:
                suggestions.append("Prefer a named function entrypoint for reusable verified units")
                flags.append("no_entrypoint")

            severity = "clean"
            if "dynamic_exec" in flags or "empty" in flags:
                severity = "block"
            elif flags:
                severity = "improve"

            critique = (
                f"[{severity}] ~{lines} lines, complexity={complexity:.2f}. "
                + ("; ".join(suggestions[:3]) if suggestions else "No structural issues flagged.")
            )

            payload = LabradoriteResponse(
                complexity_score=round(complexity, 2),
                critique=critique[:500],
                suggested_improvements=suggestions[:10],
                confidence_score=0.7 if severity == "clean" else 0.55,
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
