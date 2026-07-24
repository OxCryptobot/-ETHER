# core/schemas.py
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator
from typing import Literal, List, Optional, Union, Dict, Any
from uuid import UUID
from enum import Enum


class GemErrorType(str, Enum):
    TIMEOUT = "timeout"
    SECURITY = "security"
    COMPILE = "compile"
    RUNTIME = "runtime"
    DEPENDENCY = "dependency"
    UNKNOWN = "unknown"


class GemError(BaseModel):
    type: GemErrorType
    message: str
    recoverable: bool
    suggested_action: Optional[str] = None


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


# ---------- Clear Quartz ----------
class ClearQuartzRequest(BaseModel):
    code: str
    language: Literal["python", "javascript", "rust", "go"]
    test_cases: List[str] = Field(default_factory=list)
    sandbox_profile: Literal["fast", "strict"] = "fast"


class ClearQuartzResponse(BaseModel):
    stdout: str = ""
    stderr: str = ""
    exit_code: int
    total_tests: int = 0
    tests_passed: int = 0
    security_flags: List[str] = Field(default_factory=list)
    execution_time: float = 0.0
    static_analysis_score: float = 1.0

    @model_validator(mode="after")
    def validate_tests(self) -> "ClearQuartzResponse":
        if self.tests_passed < 0 or self.tests_passed > self.total_tests:
            raise ValueError(
                f"tests_passed ({self.tests_passed}) must be between 0 and total_tests ({self.total_tests})"
            )
        return self


# ---------- Rose Quartz ----------
class RoseQuartzRequest(BaseModel):
    messages: List[ChatMessage]
    prefer_local: bool = True
    max_tokens: int = 4096


class RoseQuartzResponse(BaseModel):
    content: str
    model_used: str
    tokens: int = 0
    confidence_score: float = 0.0


# ---------- Union types ----------
GemRequestPayload = Union[ClearQuartzRequest, RoseQuartzRequest]
GemResponsePayload = Union[ClearQuartzResponse, RoseQuartzResponse]


class Envelope(BaseModel):
    task_id: UUID
    target_gem: Literal[
        "clear-quartz",
        "rose-quartz",
        "citrine",
        "selenite",
        "amethyst",
        "black-tourmaline",
        "labradorite",
        "grandidierite",
    ]
    payload: GemRequestPayload
    timeout_seconds: int = 60  # single source of truth


class ResponseEnvelope(BaseModel):
    task_id: UUID
    source_gem: Literal[
        "clear-quartz",
        "rose-quartz",
        "citrine",
        "selenite",
        "amethyst",
        "black-tourmaline",
        "labradorite",
        "grandidierite",
    ]
    payload: Optional[GemResponsePayload] = None
    error: Optional[GemError] = None

    @model_validator(mode="after")
    def xor_error_and_payload(self) -> "ResponseEnvelope":
        if self.error is not None and self.payload is not None:
            raise ValueError("ResponseEnvelope cannot contain both error and payload")
        if self.error is None and self.payload is None:
            raise ValueError("ResponseEnvelope must contain either error or payload")
        return self
