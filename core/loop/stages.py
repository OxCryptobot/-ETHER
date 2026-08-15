"""Named pipeline stages — orchestration contract (Phase 2.3).

Does not execute anything. Gives LoopRunner / Pipeline a stable vocabulary
so strangler extraction cannot rename stages silently and break scoreboards.
"""
from __future__ import annotations

from typing import Tuple

# Canonical stage names as they appear on PipelineResult.stages[].stage
STAGE_START = "start"
STAGE_PLAN = "plan"
STAGE_TOOL_RUN = "tool_run"
STAGE_EXTEND = "extend"
STAGE_TOOL_ASSIST = "tool_assist"
STAGE_TOOL_RUNTIME = "tool_runtime"
STAGE_CONTEXT = "context"
STAGE_REPO_MAP = "repo_map"
STAGE_CODE = "code"
STAGE_CODE_RETRY = "code_retry"
STAGE_SANDBOX = "sandbox"
STAGE_SANDBOX_RETRY = "sandbox_retry"
STAGE_REPO_ORACLE = "repo_oracle"
STAGE_AGENT_LOOP = "agent_loop"
STAGE_TOOL_SCAN = "tool_scan"
STAGE_AUDIT = "audit"
STAGE_CRITIQUE = "critique"
STAGE_HOLDOUT = "holdout"
STAGE_PROMPT_GUARD = "prompt_guard"
STAGE_MEMORY_SAVE = "memory_save"
STAGE_AUTO_FABRICATE = "auto_fabricate"
STAGE_EXCEPTION = "exception"

# Preferred happy-path order under tool-first (documentation + tests)
TOOL_FIRST_ORDER: Tuple[str, ...] = (
    STAGE_PLAN,
    STAGE_TOOL_RUNTIME,
    STAGE_SANDBOX,
    STAGE_AUDIT,
    STAGE_CRITIQUE,
)

LEGACY_GENERATE_ORDER: Tuple[str, ...] = (
    STAGE_PLAN,
    STAGE_CODE,
    STAGE_SANDBOX,
    STAGE_AUDIT,
)
