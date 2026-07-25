"""Unit tests for core schemas."""

from uuid import uuid4
import pytest
from pydantic import ValidationError

from core.schemas import (
    ClearQuartzResponse,
    Envelope,
    ClearQuartzRequest,
    ResponseEnvelope,
    GemError,
    GemErrorType,
)


def test_clear_quartz_response_valid():
    r = ClearQuartzResponse(exit_code=0, total_tests=5, tests_passed=5)
    assert r.tests_passed == 5


def test_clear_quartz_response_rejects_over():
    with pytest.raises(ValidationError):
        ClearQuartzResponse(exit_code=0, total_tests=5, tests_passed=10)


def test_clear_quartz_response_rejects_negative():
    with pytest.raises(ValidationError):
        ClearQuartzResponse(exit_code=0, total_tests=5, tests_passed=-1)


def test_response_envelope_xor():
    with pytest.raises(ValidationError):
        ResponseEnvelope(
            task_id=uuid4(),
            source_gem="clear-quartz",
            payload=ClearQuartzResponse(exit_code=0),
            error=GemError(type=GemErrorType.RUNTIME, message="x", recoverable=True),
        )


def test_envelope_target_gem_literal():
    env = Envelope(
        task_id=uuid4(),
        target_gem="clear-quartz",
        payload=ClearQuartzRequest(code="print(1)"),
    )
    assert env.target_gem == "clear-quartz"
