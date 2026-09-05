"""p2 leftover: plan skip installs fix_plan; empty skip is a no-op."""
from __future__ import annotations

import inspect

from core.loop.goal import PROGRESS
from core.loop.plan_stage import apply_plan_skip, run_plan_stage, walk_current_plan
from core.pipeline import Pipeline


def test_pipeline_uses_plan_stage() -> None:
    src = inspect.getsource(Pipeline.run)
    assert "apply_plan_skip" in src
    assert "walk_current_plan" in src


def test_apply_plan_skip_false_when_empty() -> None:
    class R:
        plan = None
        plan_ok = False
        degraded: list = []

    calls: list = []

    def wp(*_a, **_k):
        calls.append(1)

    assert apply_plan_skip(set(), "fix ledger", R(), wp, "t") is False
    assert calls == []


def test_apply_plan_skip_installs_fix_plan() -> None:
    class R:
        plan = None
        plan_ok = False
        degraded: list = []

    details: list = []

    def wp(*_a, **k):
        details.append(str(k.get("detail") or ""))

    r = R()
    assert apply_plan_skip({"plan"}, "fix ledger", r, wp, "t") is True
    assert r.plan_ok is True
    assert r.plan is not None
    assert any(s.action == "observe" for s in r.plan.steps)
    assert "skipped_resume_fix_dag" in details
    assert callable(walk_current_plan)
    assert callable(run_plan_stage)
    assert PROGRESS["split_pipeline_godfile"] in {"begin_extracted", "begin_plan_extracted", "begin_plan_tools_extracted"}
