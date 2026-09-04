"""p4_03 FAST: empty/unmapped plans and fix queries use the fix-task DAG."""
from __future__ import annotations

from core.loop.plan_walk import walk_plan
from core.schemas import ExecutionPlan, PlanStep
from gems.selenite.planner import Selenite


def test_empty_plan_uses_fix_dag() -> None:
    rows = walk_plan(ExecutionPlan(steps=[], reasoning="fix ledger"))
    actions = [r["action"] for r in rows]
    assert actions[:3] == ["observe", "mutate", "test"]
    tools = [r.get("tool") for r in rows]
    assert "replace_once" in tools
    assert "run_tests" in tools


def test_unmapped_plan_stays_unmapped() -> None:
    plan = ExecutionPlan(
        steps=[PlanStep(id=1, action="understand", target="request")],
        reasoning="hello",
    )
    rows = walk_plan(plan)
    assert rows[0]["status"] == "unmapped"


def test_mapped_plan_unchanged() -> None:
    plan = ExecutionPlan(
        steps=[
            PlanStep(id=1, action="generate", target="code"),
            PlanStep(id=2, action="test", target="sandbox", deps=[1]),
        ]
    )
    rows = walk_plan(plan)
    assert [r["action"] for r in rows] == ["generate", "test"]


def test_selenite_fix_query_is_fix_dag() -> None:
    plan = Selenite()._create_plan("fix ledger unaided", 5, "")
    assert [s.action for s in plan.steps][:3] == ["observe", "mutate", "test"]
