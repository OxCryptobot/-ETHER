"""Phase 3 evolution operator — unlocked after metrics_go + hard canary."""
from __future__ import annotations

from core.phase3_evolve import draft_job_from_critique, phase3_unlocked, tick


def test_tick_never_lifts_wheels_or_soft_launch():
    out = tick(enqueue=False, force_critique=False)
    assert out.get("soft_launch") is False
    assert "unlocked" in out
    assert out.get("path")
    assert out.get("thread_id") == "phase3_evolve"


def test_draft_job_is_measure_and_not_eligible_live():
    job = draft_job_from_critique(
        {
            "root_cause": "tool_order",
            "smallest_experiment": {"change": "scripted ledger then live canary"},
        },
        job_id="p3_test_draft",
    )
    assert job["class"] == "measure"
    assert job["continue_on_fail"] is True
    argv = " ".join(job["steps"][0]["argv"])
    assert "--mode" in argv and "scripted" in argv
    assert "eligible" not in job["note"].lower() or "denied" in job["note"].lower()


def test_phase3_unlock_predicate_is_boolean():
    assert phase3_unlocked() in (True, False)
