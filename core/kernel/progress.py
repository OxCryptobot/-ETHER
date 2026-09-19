"""Honest product progress. Not marketing."""
from __future__ import annotations

LANDED = (
    "single_writer_policy", "honest_pass_gate", "job_schema", "critique_gate",
    "permissions", "briefing", "score_write", "poll_cadence", "live_drain_exe",
    "tool_constitution", "loop_guard", "attach_observe_only", "generate_cannot_pass",
    "redact", "tombstone_410", "symbol_index", "sandbox_jail", "deadline",
    "targeted_tests", "ether_md_inject",
)
REMAINING_PRODUCT = (
    "exe_process_alive_on_1650", "ollama_attached_true", "hard_live_repeatable",
    "pipeline_strangle", "structured_ollama_tools", "session_resume_ux", "isolated_gem_workers",
)
CONTRACT_PCT = 62
PRODUCT_PCT = 28

def snapshot() -> dict:
    return {
        "kernel_contracts_pct": CONTRACT_PCT,
        "product_writer_pct": PRODUCT_PCT,
        "soft_launch": "blocked",
        "wheels": "on",
        "landed": list(LANDED),
        "remaining": list(REMAINING_PRODUCT),
        "blocker": "open existing ETHER.exe on the 1650 so ollama attach is true",
    }
