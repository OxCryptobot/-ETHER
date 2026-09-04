"""p3_59: ExecutionPlan.steps walk in dep order and map onto gems."""
import inspect

from core.loop.plan_walk import TARGET_GEM, topo_sort, walk_plan
from core.pipeline import Pipeline
from core.schemas import ExecutionPlan, PlanStep


def test_topo_respects_deps():
    plan = ExecutionPlan(
        steps=[
            PlanStep(id=2, action="test", target="sandbox", deps=[1]),
            PlanStep(id=1, action="generate", target="code"),
            PlanStep(id=3, action="validate", target="security", deps=[2]),
        ]
    )
    order = [s.id for s in topo_sort(plan)]
    assert order == [1, 2, 3]


def test_walk_maps_sandbox_and_security():
    plan = ExecutionPlan(
        steps=[
            PlanStep(id=1, action="generate", target="code"),
            PlanStep(id=2, action="test", target="sandbox", deps=[1]),
            PlanStep(id=3, action="validate", target="security", deps=[2]),
        ]
    )
    rows = walk_plan(plan)
    by_action = {r["action"]: r for r in rows}
    assert by_action["generate"]["gem"] == "rose_quartz"
    assert by_action["test"]["gem"] == "clear_quartz"
    assert by_action["test"]["status"] == "live"
    assert by_action["validate"]["gem"] == "black_tourmaline"


def test_unmapped_target():
    plan = ExecutionPlan(steps=[PlanStep(id=1, action="understand", target="request")])
    rows = walk_plan(plan)
    assert rows[0]["status"] == "unmapped"
    assert rows[0]["gem"] is None


def test_pipeline_run_walks_plan():
    src = inspect.getsource(Pipeline.run)
    assert "walk_plan" in src


def test_target_aliases_cover_live_gems():
    assert TARGET_GEM["sandbox"] == "clear_quartz"
    assert TARGET_GEM["labradorite"] == "labradorite"
