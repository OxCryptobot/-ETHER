"""Critical fixes batch — do not break defaults."""
from __future__ import annotations

from core.queue_governor import MAX_PENDING, may_enqueue, status_snapshot, classify_bucket
from core.playbook_limiter import allow_playbook, mark_playbook, may_fire
from core.latency_budget import step_timeout_for_job, budgets, ratio_status
from core.honest_kpi import compute
from core.job_class import job_class, schedule_rank, MEASURE, RECOVERY, FAST, LIVE
from scripts.foreman import BATCH_SIZE, STEADY_TEMPLATES


def test_batch_size_capped():
    assert BATCH_SIZE <= 6
    assert MAX_PENDING <= 6


def test_governor_status():
    snap = status_snapshot()
    assert "pending" in snap
    assert snap["max_pending"] <= 6


def test_playbook_limiter_window():
    mark_playbook("budget_exhaust", "test_lesson")
    assert allow_playbook("budget_exhaust", "test_lesson") is False


def test_latency_live_budget_tighter_than_scripted():
    b = budgets()
    assert b["live_step_s"] <= b["scripted_step_s"]
    live_job = {"id": "ss_pipeline_ledger_x", "class": "live", "note": "live ledger"}
    scripted = {"id": "ss_pipeline_scripted_x", "class": "fast", "note": "scripted"}
    assert step_timeout_for_job(live_job) <= step_timeout_for_job(scripted)


def test_ratio_target():
    st = ratio_status(1.0, 148.4)
    assert st["ok"] is False
    st2 = ratio_status(1.0, 10.0)
    assert st2["ok"] is True


def test_honest_kpi_shape():
    out = compute(rows=[])
    assert "honest_tool_pass" in out
    assert "primary_kpi" in out


def test_job_buckets_order():
    jobs = [
        {"id": "live1", "class": "live", "note": "live ledger"},
        {"id": "meas1", "class": "measure", "note": "measure_tick"},
        {"id": "rec1", "note": "playbook:labradorite for x"},
        {"id": "fast1", "class": "fast", "note": "pytest"},
    ]
    ranked = sorted(jobs, key=schedule_rank)
    assert job_class(ranked[0]) == MEASURE
    assert job_class(ranked[1]) == RECOVERY
    assert job_class(ranked[2]) == FAST
    assert job_class(ranked[3]) == LIVE


def test_steady_measure_first():
    assert STEADY_TEMPLATES[0]["id_prefix"] == "ss_measure_tick"
    assert "ss_kill_live_pending" not in {t["id_prefix"] for t in STEADY_TEMPLATES}


def test_pipeline_still_imports():
    from core.pipeline import Pipeline

    assert Pipeline is not None
