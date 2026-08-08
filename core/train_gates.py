"""Training doctrine — Grok → ETHER apprentice rules enforced in code.

Not LoRA. Not BoN. Honest memory hygiene so the coder gets better data,
not more noise.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

# Minimum verification score to store a PASS (unless holdout_ok is True).
PASS_MIN_VERIFICATION = float(os.getenv("ETHER_PASS_MIN_VERIFICATION") or "0.99")

# Strategies ranked for few-shot preference (higher = better teacher signal).
# These are the prior. Live measurements from preference.py temper them.
STRATEGY_TRUST = {
    "tool_runtime": 3.0,
    "multifile": 1.5,
    "with_asserts": 1.2,
    "default": 1.0,
    "minimal": 0.9,
    "repair_heavy": 0.8,
    # BoN / agent_loop measured net negative — deprioritize in retrieve
    "agent_loop": 0.2,
    "best_of_n": 0.1,
}


def train_gates_enabled() -> bool:
    return (os.getenv("ETHER_TRAIN_GATES") or "1").strip() != "0"


def may_record_pass(
    *,
    success: bool,
    verification_score: float = 0.0,
    total_tests: int = 0,
    holdout_ok: Optional[bool] = None,
    confidence: float = 0.0,
) -> tuple[bool, str]:
    """Gate 1 — only store verified successes into the PASS vault."""
    if not success:
        return False, "not_success"
    if holdout_ok is False:
        return False, "holdout_failed"
    if holdout_ok is True:
        return True, "holdout_ok"
    ver = float(verification_score or 0.0)
    tests = int(total_tests or 0)
    if tests > 0 and ver >= PASS_MIN_VERIFICATION:
        return True, "verification_ok"
    if tests > 0 and ver < PASS_MIN_VERIFICATION:
        return False, "verification_too_low"
    # No tests and no holdout — refuse (prevents conf=1.0 theatre)
    if tests <= 0 and holdout_ok is None:
        return False, "unverified_no_tests"
    return False, "unverified"


def may_record_fail(
    *,
    success: bool,
    stderr: str = "",
    fail_kind: str = "",
) -> tuple[bool, str]:
    """Gate 4 — log code failures only, not infra outages."""
    if success:
        return False, "not_fail"
    fk = (fail_kind or "").strip().lower()
    if fk in ("dependency", "plan", "exception", "infra", "timeout_infra"):
        return False, "infra_fail_kind"
    low = (stderr or "").lower()
    infra_sigs = (
        "cannot connect to the docker daemon",
        "failed to connect to the docker api",
        "cannot connect to ollama",
        "connection refused",
        "max retries exceeded",
        "name or service not known",
        "no such host",
        "read timed out",
    )
    if any(s in low for s in infra_sigs):
        return False, "infra_stderr"
    return True, "code_failure"


def strategy_boost(strategy: str) -> float:
    """Gate 3 — prefer tool_runtime traces; now tempered by live measured win rates."""
    try:
        from core.preference import live_strategy_boost

        return float(live_strategy_boost(strategy))
    except Exception:
        return float(STRATEGY_TRUST.get((strategy or "").strip(), 1.0))


def classify_fail_kind(stderr: str, explicit: str = "") -> str:
    """Normalize fail_kind for curriculum (code signal, not infra)."""
    if explicit and explicit.strip():
        return explicit.strip()
    low = (stderr or "").lower()
    if "syntaxerror" in low or "indentationerror" in low:
        return "SyntaxError"
    if "nameerror" in low:
        return "NameError"
    if "typeerror" in low:
        return "TypeError"
    if "assertionerror" in low or "assert" in low:
        return "AssertionError"
    if "timeout" in low:
        return "timeout"
    if any(s in low for s in ("docker", "ollama", "connection refused")):
        return "infra"
    return "runtime"


def doctrine_summary() -> Dict[str, Any]:
    live = {}
    try:
        from core.preference import preference_summary

        live = preference_summary()
    except Exception:
        pass
    return {
        "pass_min_verification": PASS_MIN_VERIFICATION,
        "strategy_trust": dict(STRATEGY_TRUST),
        "live_strategy_stats": live,
        "enabled": train_gates_enabled(),
        "teacher": "grok",
        "rules": [
            "only_verified_pass",
            "reject_leaky_few_shot",
            "prefer_tool_runtime",
            "no_infra_as_code_fail",
            "learn_from_measured_preferences",
        ],
    }
