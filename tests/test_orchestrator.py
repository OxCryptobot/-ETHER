"""Unit tests for orchestrator state machine."""

from uuid import uuid4

from core.orchestrator import Orchestrator, Status
from core.schemas import (
    Envelope,
    ResponseEnvelope,
    ClearQuartzRequest,
    ClearQuartzResponse,
    GemError,
    GemErrorType,
)


def _req():
    return Envelope(
        task_id=uuid4(),
        target_gem="clear-quartz",
        payload=ClearQuartzRequest(code="print(1)"),
    )


def _ok(task_id):
    return ResponseEnvelope(
        task_id=task_id,
        source_gem="clear-quartz",
        payload=ClearQuartzResponse(exit_code=0),
    )


def _err(task_id, recoverable=True):
    return ResponseEnvelope(
        task_id=task_id,
        source_gem="clear-quartz",
        error=GemError(
            type=GemErrorType.TIMEOUT if recoverable else GemErrorType.SECURITY,
            message="test error",
            recoverable=recoverable,
        ),
    )


def test_happy_path():
    orch = Orchestrator()
    req = _req()
    orch.start(req.task_id)
    assert orch.state.status == Status.PLANNING

    assert orch.process_response(req, _ok(req.task_id)) == Status.EXECUTING
    assert orch.process_response(req, _ok(req.task_id)) == Status.VALIDATING
    assert orch.process_response(req, _ok(req.task_id)) == Status.AUDITING
    assert orch.process_response(req, _ok(req.task_id)) == Status.COMPLETE


def test_recoverable_retry():
    orch = Orchestrator()
    req = _req()
    orch.start(req.task_id)
    orch.process_response(req, _ok(req.task_id))  # planning -> executing
    status = orch.process_response(req, _err(req.task_id, recoverable=True))
    assert status == Status.PLANNING
    assert orch.state.retry_count == 1


def test_non_recoverable_immediate_error():
    orch = Orchestrator()
    req = _req()
    orch.start(req.task_id)
    status = orch.process_response(req, _err(req.task_id, recoverable=False))
    assert status == Status.ERROR


def test_task_id_mismatch_raises():
    orch = Orchestrator()
    req = _req()
    orch.start(req.task_id)
    bad = _ok(uuid4())
    try:
        orch.process_response(req, bad)
        assert False, "should have raised"
    except ValueError as e:
        assert "mismatch" in str(e).lower()
