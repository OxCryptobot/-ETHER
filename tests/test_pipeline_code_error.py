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


class OkPlan:
    def execute(self, request: Envelope) -> ResponseEnvelope:
        return ResponseEnvelope(
            task_id=request.task_id,
            source_gem="selenite",
            payload=SeleniteResponse(plan=ExecutionPlan(steps=[PlanStep(id=1, action="generate", target="code", description="g")])),
        )


class BoomCode:
    def execute(self, request: Envelope) -> ResponseEnvelope:
        return ResponseEnvelope(
            task_id=request.task_id,
            source_gem="rose-quartz",
            error=GemError(type=GemErrorType.DEPENDENCY, message="ollama down", recoverable=True),
        )


def test_pipeline_code_stage_failure():
    reg = GemRegistry()
    reg.register("selenite", OkPlan())
    reg.register("rose-quartz", BoomCode())
    result = Pipeline(registry=reg).run("write hello")
    assert result.status == "error"
    assert any(s.stage == "code" and not s.success for s in result.stages)
