"""p2 FAST: pep8 loop scope + resume skip includes plan."""
from __future__ import annotations

import inspect

from core.checkpoint import AgentCheckpoint
from core.loop.resume import should_skip
from core.pipeline import Pipeline
from scripts.pep8_loop import SCOPE, review


def test_plan_is_skippable() -> None:
    prior = AgentCheckpoint(run_id="t", stage="pipeline:plan")
    assert should_skip("plan", prior) is True
    assert should_skip("sandbox", prior) is False


def test_pipeline_run_honors_plan_skip() -> None:
    src = inspect.getsource(Pipeline.run)
    assert "skipped_resume_fix_dag" in src
    assert "fix_plan" in src


def test_pep8_scope_exists() -> None:
    assert "core/loop" in SCOPE
    payload = review()
    assert payload["n_critical"] == 0
    assert payload["ok"] is True
