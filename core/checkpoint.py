"""Checkpoint / resume schema for long agent runs.

Wired into ToolRuntime.run after every step (P3).
Wired into Pipeline.run via checkpoint_pipeline at each write_progress.
LoopRunner default-on is still the next strangler slice.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
CKPT_DIR = ROOT / "artifacts" / "checkpoints"


@dataclass
class AgentCheckpoint:
    run_id: str
    stage: str
    objective: str = ""
    n_steps: int = 0
    best_score: float = 0.0
    messages_tail: List[Dict[str, str]] = field(default_factory=list)
    workspace_hint: str = ""
    failure_type: str = ""
    created: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if not d.get("created"):
            d["created"] = datetime.now(timezone.utc).isoformat()
        return d


def save_checkpoint(ckpt: AgentCheckpoint) -> Path:
    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    path = CKPT_DIR / f"{ckpt.run_id}.json"
    path.write_text(json.dumps(ckpt.to_dict(), indent=2), encoding="utf-8")
    return path


def load_checkpoint(run_id: str) -> Optional[AgentCheckpoint]:
    path = CKPT_DIR / f"{run_id}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return AgentCheckpoint(
        run_id=str(data.get("run_id") or run_id),
        stage=str(data.get("stage") or ""),
        objective=str(data.get("objective") or ""),
        n_steps=int(data.get("n_steps") or 0),
        best_score=float(data.get("best_score") or 0.0),
        messages_tail=list(data.get("messages_tail") or []),
        workspace_hint=str(data.get("workspace_hint") or ""),
        failure_type=str(data.get("failure_type") or ""),
        created=str(data.get("created") or ""),
        extra=dict(data.get("extra") or {}),
    )


def checkpoint_step(
    *,
    run_id: str,
    stage: str,
    objective: str = "",
    n_steps: int = 0,
    best_score: float = 0.0,
    messages_tail: Optional[List[Dict[str, str]]] = None,
    workspace_hint: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    """Best-effort write. Never raise into the agent loop."""
    try:
        rid = (run_id or "tool_runtime").replace("/", "_")[:80]
        return save_checkpoint(
            AgentCheckpoint(
                run_id=rid,
                stage=stage[:80],
                objective=(objective or "")[:500],
                n_steps=int(n_steps),
                best_score=float(best_score),
                messages_tail=list(messages_tail or [])[-6:],
                workspace_hint=(workspace_hint or "")[:240],
                extra=dict(extra or {}),
            )
        )
    except Exception:
        return None


def checkpoint_pipeline(
    *,
    run_id: str,
    stage: str,
    objective: str = "",
    n_stages: int = 0,
    extra: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    """Pipeline.run hook. Same on-disk schema, stage prefixed so runtimes do not collide."""
    payload = dict(extra or {})
    payload.setdefault("kind", "pipeline")
    return checkpoint_step(
        run_id=f"pipeline-{run_id}",
        stage=f"pipeline:{stage}"[:80],
        objective=objective,
        n_steps=int(n_stages),
        extra=payload,
    )
