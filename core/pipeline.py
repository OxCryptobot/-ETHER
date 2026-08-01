"""End-to-end pipeline: experience, process rewards, burst-on-retry, multifile assist."""

from __future__ import annotations

import inspect
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple
from uuid import uuid4, UUID

from pydantic import BaseModel, Field

from core.schemas import (
    Envelope,
    SeleniteRequest,
    SeleniteResponse,
    RoseQuartzRequest,
    RoseQuartzResponse,
    ClearQuartzRequest,
    ClearQuartzResponse,
    BlackTourmalineRequest,
    BlackTourmalineResponse,
    LabradoriteRequest,
    LabradoriteResponse,
    AmethystRequest,
    GrandidieriteRequest,
    ChatMessage,
    ExecutionPlan,
)
from core.registry import GemRegistry, build_default_registry
from core.orchestrator import Orchestrator
from core.confidence import compute_scores
from core.context import gather_workspace_context, context_enabled
from core.learning import (
    BanditPolicy,
    arm_behaviour,
    compute_reward,
    learning_enabled,
    strategy_prompt_addon,
)
from core.fail_streak import record_outcome, maybe_propose_fabricate
from core.progress import write_progress, clear_progress
from core.repair import repair_prompt, classify_stderr
from core.patterns import index_pass_pattern
from core.experience import retrieve as experience_retrieve, record as experience_record
from core.bench_guardian import is_frozen
from core.pipeline_burst import decide_burst
from core.pipeline_select import current_tier, select_strategy_with_context
from core.loop import loop_runner_enabled
from core.loop.handlers.finalize import FinalizeContext
from core.loop.handlers.verify import VerificationContext
from core.loop.runner import LoopRunner
from core.spine.state_io import write_json

MAX_CODE_CHARS = 50_000


class _LoopAlreadyGenerated(Exception):
    """Control flow: the agent loop produced the artifact; skip legacy generation."""


@dataclass
class _Attempt:
    """One generation attempt = one bandit decision."""

    strategy: str
    context: Dict[str, Any] = field(default_factory=dict)
    credited: bool = False


class StageResult(BaseModel):
    stage: str
    success: bool
    detail: str = ""
    duration_ms: float = 0.0


class PipelineResult(BaseModel):
    task_id: UUID
    objective: str
    plan: Optional[ExecutionPlan] = None
    generated_code: Optional[str] = None
    sandbox: Optional[ClearQuartzResponse] = None
    audit: Optional[BlackTourmalineResponse] = None
    critique: Optional[LabradoriteResponse] = None
    holdout_ok: Optional[bool] = None
    # Phase B: set when ETHER_REPO_ORACLE is active; False forces repair/retry.
    repo_oracle_ok: Optional[bool] = None
    confidence: float = 0.0
    execution_score: float = 0.0
    verification_score: float = 0.0
    status: str = "complete"
    error: Optional[str] = None
    stages: List[StageResult] = Field(default_factory=list)
    degraded: List[str] = Field(default=[])
    retries: int = 0
    context_chars: int = 0
    strategy: str = "default"
    strategies: List[str] = Field(default_factory=list)
    reward: float = 0.0
    few_shot_chars: int = 0
    tool_output_chars: int = 0
    experience_chars: int = 0
    used_burst: bool = False
    first_compile_ok: bool = False
    plan_ok: bool = False
    started_at: str = ""
    finished_at: str = ""
