"""Skip completed Pipeline stages when a checkpoint exists.

Phase 2 slice. Pipeline.run still walks; this is the skip set it can consult.
Does not spawn a second agent.
"""
from __future__ import annotations

from typing import FrozenSet, Optional

from core.checkpoint import AgentCheckpoint

STAGE_ORDER = (
    "start",
    "gems",
    "plan",
    "plan_walk",
    "code",
    "sandbox",
    "verify",
    "done",
)


def normalize_stage(stage: str) -> str:
    s = (stage or "").strip()
    if s.startswith("pipeline:"):
        s = s.split(":", 1)[1]
    return s.split(":")[0]


def skipped_stages(prior: Optional[AgentCheckpoint]) -> FrozenSet[str]:
    if prior is None:
        return frozenset()
    stage = normalize_stage(prior.stage)
    if stage not in STAGE_ORDER:
        return frozenset()
    idx = STAGE_ORDER.index(stage)
    return frozenset(STAGE_ORDER[: idx + 1])


def should_skip(stage: str, prior: Optional[AgentCheckpoint]) -> bool:
    return normalize_stage(stage) in skipped_stages(prior)
