"""p2 leftover: plan skip/walk extracted; skipped plan does not read plan_res."""
from __future__ import annotations

import inspect

from core.loop.goal import PROGRESS
from core.loop.plan_stage import apply_plan_skip, walk_current_plan
from core.pipeline import Pipeline


def test_pipeline_uses_plan_stage() -> None:
    src = inspect.getsource(Pipeline.run)
    assert "apply_plan_skip" in src
    assert "walk_current_plan" in src
    assert "plan_res is not None" in src


def test_apply_plan_skip_false_when_empty() -> None:
    class R:
        plan = None
        plan_ok = False

    calls = []

    def wp(*a, **k):
        calls.append((a, k))

    assert apply_plan_skip(set(), "fix ledger", R(), wp, "t") is False
    assert calls == []


def test_walk_callable() -> None:
    assert callable(walk_current_plan)
    assert PROGRESS["split_pipeline_godfile"] in {"begin_extracted", "begin_plan_extracted"}
