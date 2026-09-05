"""p2 leftover: begin_run extracts start/resume/gems off Pipeline.run."""
from __future__ import annotations

import inspect

from core.loop.begin import start_resume_gems
from core.loop.goal import PROGRESS, current
from core.pipeline import Pipeline


def test_pipeline_run_calls_begin() -> None:
    src = inspect.getsource(Pipeline.run)
    assert "start_resume_gems" in src


def test_start_resume_gems_callable() -> None:
    assert callable(start_resume_gems)


def test_goal_progress_begin_extracted() -> None:
    g = current()
    assert g["progress"]["leftover_reverify"] == "PASS"
    assert PROGRESS["split_pipeline_godfile"] in {"begin_extracted", "begin_plan_extracted", "begin_plan_tools_extracted", "begin_plan_tools_mark_extracted", "gems_call_extracted"}
    assert g["living_gate"]["met"] is True
