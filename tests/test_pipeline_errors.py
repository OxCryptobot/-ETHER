from uuid import uuid4
from core.pipeline import Pipeline
from core.registry import GemRegistry
from core.schemas import (
    Envelope,
    ResponseEnvelope,
    SeleniteResponse,
    ExecutionPlan,
    PlanStep,
    GemError,
    GemErrorType,
)


class BoomPlan:
    def execute(self, request: Envelope) -> ResponseEnvelope:
        return ResponseEnvelope(
            task_id=request.task_id,
            source_gem="selenite",
            error=GemError(type=GemErrorType.RUNTIME, message="plan boom", recoverable=True),
        )


def test_pipeline_plan_failure():
    reg = GemRegistry()
    reg.register("selenite", BoomPlan())
    # minimal stubs so later stages aren't required
    result = Pipeline(registry=reg).run("x")
    assert result.status == "error"
    assert "plan" in (result.error or "").lower() or result.stages[0].stage == "plan"
