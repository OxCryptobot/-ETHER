"""p3_61–66: seven-phase slice that fits this host. No swarm. No LoRA."""
import inspect
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.checkpoint import resume_if_any
from core.critique_on_fail import critique_fail
from core.loop.git_tools import git_diff, git_status
from core.loop.medic import medic_stand_down
from core.loop.plan_exec import dispatch_walked, tool_for_step
from core.loop.plan_walk import walk_plan
from core.pipeline import Pipeline
from core.schemas import ExecutionPlan, PlanStep


def test_live_sandbox_test_maps_run_tests():
    row = {"gem": "clear_quartz", "action": "test", "status": "live"}
    assert tool_for_step(row) == "run_tests"


def test_theatre_step_does_not_dispatch_tool():
    row = {"gem": "selenite", "action": "analyze", "status": "theatre"}
    assert tool_for_step(row) is None


def test_dispatch_walked_marks_run_tests():
    plan = ExecutionPlan(
        steps=[
            PlanStep(id=1, action="generate", target="code"),
            PlanStep(id=2, action="test", target="sandbox", deps=[1]),
        ]
    )
    rows = dispatch_walked(walk_plan(plan))
    by = {r["action"]: r for r in rows}
    assert by["test"]["tool"] == "run_tests"
    assert by["generate"]["dispatched"] == "record"


def test_pipeline_source_resume_and_dispatch():
    src = inspect.getsource(Pipeline.run)
    assert "resume_if_any" in src
    assert "dispatch_walked" in src


def test_resume_missing_is_none():
    assert resume_if_any("no-such-run") is None


def test_critique_skips_teacher_when_policy_model(monkeypatch, tmp_path):
    monkeypatch.setenv("ETHER_LIVE_POLICY", "model")
    monkeypatch.setenv("ETHER_ROOT", str(tmp_path))
    art = critique_fail(job_id="x", failure_type="logic", note="fail", enqueue=True)
    if art.get("skipped"):
        return
    assert art.get("enqueue_skipped") == "policy_model"
    assert art.get("enqueued") in (None, False)


def test_git_status_callable():
    st = git_status()
    assert "ok" in st or "stdout" in st or "error" in st


def test_medic_stands_down_on_fresh_idle():
    now = datetime.now(timezone.utc)
    beat = (now - timedelta(seconds=30)).isoformat()
    assert medic_stand_down({"phase": "idle", "heartbeat": beat}, now=now) is True


def test_medic_farms_when_stale():
    now = datetime.now(timezone.utc)
    beat = (now - timedelta(minutes=20)).isoformat()
    assert medic_stand_down({"phase": "idle", "heartbeat": beat}, now=now) is False


def test_no_phase8_status_theatre():
    root = Path(__file__).resolve().parents[1]
    banned = list((root / "core").glob("phase8*_status.py")) + list((root / "core").glob("phase9*_status.py"))
    assert banned == []
