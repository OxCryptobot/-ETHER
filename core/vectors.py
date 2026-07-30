"""Typed edges between loop vertices — the audit's 'vector points' (A-3, A-4).

Stage-1 note: nothing emits Vector yet on the default path; the schema plus
`PipelineResult.degraded` are the committed envelope fields so stage 2+
handlers can adopt Vector without another schema migration.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

VertexID = Literal[
    "selenite",
    "rose-quartz",
    "clear-quartz",
    "black-tourmaline",
    "citrine",
    "amethyst",
    "labradorite",
    "grandidierite",
    "runner",
    "spine",
    "cli",
]

EdgeKind = Literal[
    "plan",
    "generate",
    "execute",
    "audit",
    "critique",
    "retrieve",
    "record",
    "fabricate",
    "promote",
    "gate",
    "verdict",
]


def prompt_hash(text: str) -> str:
    """sha256[:16] of the exact prompt sent — provenance, not caching."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: Optional[str] = None  # e.g. "qwen2.5-coder:3b" or burst label
    seed: Optional[int] = None  # per-request pinned seed
    prompt_hash: Optional[str] = None  # output of prompt_hash()
    backend: Optional[str] = None  # "docker" | "local" | "burst"


class Vector(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    vector_id: UUID = Field(default_factory=uuid4)
    trace_id: UUID  # == PipelineResult.task_id
    seq: int  # edge ordinal within the trace
    loop: Literal["L1", "L2"]
    from_vertex: VertexID
    to_vertex: VertexID
    edge_kind: EdgeKind
    payload_type: str  # e.g. "SeleniteResponse"
    payload: Dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance = Field(default_factory=Provenance)
    degraded: List[str] = Field(default_factory=list)  # A-3: capability loss, visible
    confidence: float = 0.0
    verification_score: Optional[float] = None  # set only by Spine gates
    duration_ms: float = 0.0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
