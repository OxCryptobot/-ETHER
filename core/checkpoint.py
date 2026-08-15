"""Checkpoint / resume schema for long agent runs (P3 foundation).

Not fully wired into Pipeline yet — schema + disk helpers only.
Use when a ToolRuntime or Pipeline run exceeds soft time budgets.
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
