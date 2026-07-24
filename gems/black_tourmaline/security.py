"""Black Tourmaline — security scanning and policy enforcement."""

from __future__ import annotations

import ast
import re
from typing import List

from core.schemas import (
    Envelope,
    ResponseEnvelope,
    GemError,
    GemErrorType,
    BlackTourmalineRequest,
    BlackTourmalineResponse,
    PolicyViolation,
)


class BlackTourmaline:
    """Static security and policy checks."""

    FORBIDDEN_PATTERNS = [
        (r"eval\s*\(", "dangerous_eval"),
        (r"exec\s*\(", "dangerous_exec"),
        (r"__import__\s*\(", "dangerous_import"),
        (r"os\.system\s*\(", "os_system"),
        (r"subprocess\.(?:call|run|Popen)", "subprocess"),
    ]

    def execute(self, request: Envelope) -> ResponseEnvelope:
        try:
            if isinstance(request.payload, BlackTourmalineRequest):
                artifact = request.payload.artifact
            else:
                data = request.payload.model_dump() if hasattr(request.payload, "model_dump") else {}
                artifact = data.get("artifact", "")

            violations = self._scan(artifact)
            risk = min(1.0, len(violations) * 0.35)
            approved = risk < 0.5

            payload = BlackTourmalineResponse(
                approved=approved,
                violations=violations,
                risk_score=round(risk, 2),
            )

            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="black-tourmaline",
                payload=payload,
            )
        except Exception as e:
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="black-tourmaline",
                error=GemError(type=GemErrorType.RUNTIME, message=str(e), recoverable=True),
            )

    def _scan(self, code: str) -> List[PolicyViolation]:
        violations: List[PolicyViolation] = []

        for pattern, rule in self.FORBIDDEN_PATTERNS:
            if re.search(pattern, code):
                violations.append(
                    PolicyViolation(
                        rule=rule,
                        severity="high",
                        message=f"Matched forbidden pattern: {rule}",
                    )
                )

        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id in {"eval", "exec", "compile"}:
                        violations.append(
                            PolicyViolation(
                                rule=f"ast_{node.func.id}",
                                severity="critical",
                                message=f"AST detected call to {node.func.id}",
                            )
                        )
        except SyntaxError:
            violations.append(
                PolicyViolation(rule="syntax_error", severity="medium", message="Code has syntax errors")
            )

        return violations
