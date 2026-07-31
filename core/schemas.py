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
    language: Literal["python", "javascript", "rust", "go"] = "python"
    test_cases: List[str] = Field(default_factory=list)
    sandbox_profile: Literal["fast", "strict"] = "fast"
    # The originating objective. test_synth derives its only genuinely
    # falsifiable assertions by matching `name(args) == value` against this;
    # the sandbox previously hardcoded objective="" so that branch could never
    # fire and every synthesized assert was a tautology.
    objective: str = ""


class ClearQuartzResponse(BaseModel):
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
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
    # Per-request sampling overrides. These were environment-only, which made
    # best-of-N impossible: the agent loop needs a LOW temperature on the first
    # attempt and higher ones after, and mutating os.environ per call is
    # process-global and races with the batch queue. None = fall back to the
    # ETHER_TEMPERATURE / ETHER_SEED defaults.
    temperature: Optional[float] = None
    seed: Optional[int] = None


class RoseQuartzResponse(BaseModel):
    content: str
    model_used: str
    tokens: int = 0
    confidence_score: float = 0.0


# ---------- Citrine ----------
class CitrineRequest(BaseModel):
    action: Literal["search", "add", "delete", "health"] = "search"
    query: Optional[str] = None
    collection: str = "ether_code"
    top_k: int = 5
    documents: Optional[List[Dict[str, Any]]] = None
    filters: Dict[str, Any] = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    id: str
    text: str
    score: float
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CitrineResponse(BaseModel):
    results: List[RetrievalResult] = Field(default_factory=list)
    collection: str = "ether_code"
    action: str = "search"


# ---------- Selenite ----------
class PlanStep(BaseModel):
    id: int
    action: str
    target: str
    deps: List[int] = Field(default_factory=list)
    description: str = ""


class ExecutionPlan(BaseModel):
    steps: List[PlanStep] = Field(default_factory=list)
    reasoning: str = ""


class SeleniteRequest(BaseModel):
    user_query: str
    available_tools: List[str] = Field(default_factory=list)
    context: List[Dict[str, Any]] = Field(default_factory=list)
    max_plan_depth: int = 5


class SeleniteResponse(BaseModel):
    plan: ExecutionPlan
    needs_tool: bool = False
    tool_request: Optional[Dict[str, Any]] = None
    confidence_score: float = 0.7


# ---------- Amethyst ----------
class AmethystRequest(BaseModel):
    action: Literal["log", "analyze", "recommend"] = "log"
    interaction: Dict[str, Any] = Field(default_factory=dict)


class AmethystResponse(BaseModel):
    status: str
    recommendation: Optional[str] = None


# ---------- Black Tourmaline ----------
class BlackTourmalineRequest(BaseModel):
    artifact: str
    artifact_type: Literal["code", "tool", "config", "plan"] = "code"
    policy_profile: Literal["strict", "standard"] = "standard"


class PolicyViolation(BaseModel):
    rule: str
    severity: str
    message: str


class BlackTourmalineResponse(BaseModel):
    approved: bool
    violations: List[PolicyViolation] = Field(default_factory=list)
    risk_score: float = 0.0


# ---------- Labradorite ----------
class LabradoriteRequest(BaseModel):
    code: str
    language: str = "python"
    baseline: Optional[str] = None


class LabradoriteResponse(BaseModel):
    complexity_score: float = 0.5
    critique: str = ""
    suggested_improvements: List[str] = Field(default_factory=list)
    confidence_score: float = 0.6


# ---------- Grandidierite ----------
class GrandidieriteRequest(BaseModel):
    tool_request: Dict[str, Any] = Field(default_factory=dict)
    template_id: str = "basic_python_tool"
    context: Dict[str, Any] = Field(default_factory=dict)


class GrandidieriteResponse(BaseModel):
    generated_code: str = ""
    template_used: str = ""
    validation_status: Literal["pending", "passed", "failed"] = "pending"


# ---------- Unions ----------
GemRequestPayload = Union[
    ClearQuartzRequest,
    RoseQuartzRequest,
    CitrineRequest,
    SeleniteRequest,
    AmethystRequest,
    BlackTourmalineRequest,
    LabradoriteRequest,
    GrandidieriteRequest,
]

GemResponsePayload = Union[
    ClearQuartzResponse,
    RoseQuartzResponse,
    CitrineResponse,
    SeleniteResponse,
    AmethystResponse,
    BlackTourmalineResponse,
    LabradoriteResponse,
    GrandidieriteResponse,
]


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
    timeout_seconds: int = 60


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
