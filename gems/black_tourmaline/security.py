"""Black Tourmaline — security scanning using manifest patterns."""

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
from core.config import load_config


class BlackTourmaline:
    """Static security and policy checks driven by manifest."""

    def __init__(self):
        cfg = load_config()
        self.patterns = list(cfg.grandidierite.forbidden_patterns)
        # Always include core dangerous calls
        self.patterns.extend([
            r"eval\s*\(",
            r"exec\s*\(",
            r"__import__\s*\(",
            r"os\.system\s*\(",
            r"subprocess\.(?:call|run|Popen)",
        ])

    def execute(self, request: Envelope) -> ResponseEnvelope:
        try:
            if isinstance(request.payload, BlackTourmalineRequest):
                artifact = request.payload.artifact
            else:
                data = request.payload.model_dump() if hasattr(request.payload, "model_dump") else {}
                artifact = data.get("artifact", "")

            violations = self._scan(artifact)
            risk = min(1.0, len(violations) * 0.35)
            # Previously `risk < 0.5`, which meant a SINGLE violation (0.35)
            # was auto-approved: os.system(...), subprocess.run(...) and
            # subprocess.Popen(...) all passed the only audit gate in the
            # system. `eval` was caught solely because it happened to match
            # three patterns. One violation is a violation.
            approved = not violations

            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="black-tourmaline",
                payload=BlackTourmalineResponse(
                    approved=approved,
                    violations=violations,
                    risk_score=round(risk, 2),
                ),
            )
        except Exception as e:
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="black-tourmaline",
                error=GemError(type=GemErrorType.RUNTIME, message=str(e), recoverable=True),
            )

    def _scan(self, code: str) -> List[PolicyViolation]:
        violations: List[PolicyViolation] = []

        for pattern in self.patterns:
            try:
                if re.search(pattern, code):
                    violations.append(
                        PolicyViolation(
                            rule=pattern[:40],
                            severity="high",
                            message=f"Matched forbidden pattern: {pattern}",
                        )
                    )
            except re.error:
                continue

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
