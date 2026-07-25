"""Integration-style test with a tiny fake registry."""

from uuid import uuid4
from core.schemas import (
    Envelope,
    ResponseEnvelope,
    SeleniteRequest,
    SeleniteResponse,
    RoseQuartzRequest,
    RoseQuartzResponse,
    ClearQuartzRequest,
    ClearQuartzResponse,
    BlackTourmalineRequest,
    BlackTourmalineResponse,
    AmethystRequest,
    AmethystResponse,
    ExecutionPlan,
    PlanStep,
)
from core.pipeline import Pipeline
from core.registry import GemRegistry


class FakeGem:
    def __init__(self, name: str):
        self.name = name

    def execute(self, request: Envelope) -> ResponseEnvelope:
        if self.name == "selenite":
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="selenite",
                payload=SeleniteResponse(
                    plan=ExecutionPlan(steps=[PlanStep(id=1, action="generate", target="code", description="gen")]),
                ),
            )
        if self.name == "rose-quartz":
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="rose-quartz",
                payload=RoseQuartzResponse(content="def hello():\n    return 'hi'\n", model_used="fake"),
            )
        if self.name == "clear-quartz":
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="clear-quartz",
                payload=ClearQuartzResponse(exit_code=0, total_tests=0, tests_passed=0),
            )
        if self.name == "black-tourmaline":
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="black-tourmaline",
                payload=BlackTourmalineResponse(approved=True, risk_score=0.0),
            )
        if self.name == "amethyst":
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="amethyst",
                payload=AmethystResponse(status="logged"),
            )
        return ResponseEnvelope(
            task_id=request.task_id,
            source_gem=self.name,  # type: ignore
            payload=AmethystResponse(status="noop"),
        )


def test_pipeline_happy_path_mocked():
    reg = GemRegistry()
    for name in ["selenite", "rose-quartz", "clear-quartz", "black-tourmaline", "amethyst"]:
        reg.register(name, FakeGem(name))

    pipe = Pipeline(registry=reg)
    result = pipe.run("write hello")
    assert result.status == "complete"
    assert result.generated_code is not None
    assert "hello" in result.generated_code
    assert result.sandbox is not None
    assert result.audit is not None
    assert result.audit.approved is True
