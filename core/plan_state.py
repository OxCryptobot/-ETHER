"""PlanState — adaptive one-step replan under training wheels.

Phase 2: confidence estimation + typed replan. Not a full task graph yet.
One hypothesis at a time; replan only on measured FAIL with a smaller next step.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# Confidence penalties by typed failure (doctrine-aligned)
_FAIL_PENALTY = {
    "timeout": 0.35,
    "budget_exhaust": 0.40,
    "max_steps": 0.40,
    "no_progress": 0.45,
    "tool_runtime_failed_terminal": 0.50,
    "live_fail": 0.40,
    "parse_fail": 0.30,
    "step_fail": 0.25,
    "exception": 0.20,
    "unknown": 0.15,
}

_REPLAN_HINT = {
    "timeout": "shrink wall budget; scripted tool_runtime only; one file",
    "budget_exhaust": "cap max_steps; force read_file tests before any write",
    "max_steps": "cap max_steps; force read_file tests before any write",
    "no_progress": "re-read failing test; single apply_patch; abort after one stagnant",
    "tool_runtime_failed_terminal": "no generate-fallback; diagnose AST/parse; scripted hard",
    "live_fail": "drop to scripted hard; measure honest tool-path only",
    "parse_fail": "fix JSON tool schema; one tool call per turn",
    "step_fail": "isolate failing step; FAST reverify",
}


@dataclass
class PlanState:
    """Durable-enough plan cursor for one objective under training wheels."""

    objective: str = ""
    hypothesis: str = ""
    confidence: float = 0.55
    cycle: int = 0
    last_failure_type: Optional[str] = None
    history: List[str] = field(default_factory=list)
    training_wheels: bool = True

    def observe_pass(self, note: str = "") -> None:
        self.confidence = min(1.0, self.confidence + 0.12)
        self.last_failure_type = None
        self.cycle += 1
        if note:
            self.history.append(f"PASS:{note[:80]}")
        self.history = self.history[-12:]

    def observe_fail(self, failure_type: str, note: str = "") -> None:
        ft = (failure_type or "unknown").strip().lower()
        pen = _FAIL_PENALTY.get(ft, 0.2)
        self.confidence = max(0.05, self.confidence - pen)
        self.last_failure_type = ft
        self.cycle += 1
        self.history.append(f"FAIL:{ft}:{note[:60]}")
        self.history = self.history[-12:]

    def should_replan(self) -> bool:
        if not self.last_failure_type:
            return False
        if self.training_wheels and self.cycle > 0:
            return True
        return self.confidence < 0.45

    def replan(self) -> Dict[str, Any]:
        """One-step replan: smaller next hypothesis from typed FAIL."""
        ft = self.last_failure_type or "unknown"
        hint = _REPLAN_HINT.get(ft, "smallest experiment: tests-first surgical patch")
        self.hypothesis = hint
        # Slight recovery of confidence after committing a smaller plan
        self.confidence = min(0.55, self.confidence + 0.05)
        return {
            "ok": True,
            "replan": True,
            "failure_type": ft,
            "hypothesis": self.hypothesis,
            "confidence": round(self.confidence, 3),
            "cycle": self.cycle,
        }

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["confidence"] = round(float(self.confidence), 3)
        return d


def plan_from_failure(
    *,
    objective: str,
    failure_type: str,
    prior_confidence: float = 0.55,
    training_wheels: bool = True,
) -> Dict[str, Any]:
    """Factory used by evolution / host critique path."""
    state = PlanState(
        objective=(objective or "")[:400],
        confidence=float(prior_confidence),
        training_wheels=training_wheels,
    )
    state.observe_fail(failure_type, note=objective[:60])
    if state.should_replan():
        return state.replan()
    return {
        "ok": True,
        "replan": False,
        "failure_type": failure_type,
        "hypothesis": state.hypothesis or "continue current hypothesis",
        "confidence": round(state.confidence, 3),
        "cycle": state.cycle,
    }
