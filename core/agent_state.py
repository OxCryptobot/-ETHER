"""Durable AgentState — shared across all GEMS.

This is the single source of truth for "what am I doing right now".
Every gem reads and writes the same object. Survives host restarts via
artifacts/agent_state/<thread_id>.json.

Training wheels: one primary hypothesis visible; Labradorite critique is
always carried forward.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "artifacts" / "agent_state"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentState:
    """Minimal durable state shared by the gem topology."""

    def __init__(self, thread_id: str = "") -> None:
        self.thread_id = thread_id or str(uuid4())[:12]
        self.created = _now()
        self.updated = self.created
        self.objective: str = ""
        self.hypothesis: str = ""
        self.root_cause: Optional[str] = None
        self.last_critique: str = ""
        self.plan_steps: List[Dict[str, Any]] = []
        self.tool_results: List[Dict[str, Any]] = []
        self.open_files: List[str] = []
        self.working_set: List[str] = []
        self.introspection: Optional[Dict[str, Any]] = None
        self.training_wheels: bool = True
        self.meta: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "created": self.created,
            "updated": self.updated,
            "objective": self.objective,
            "hypothesis": self.hypothesis,
            "root_cause": self.root_cause,
            "last_critique": self.last_critique,
            "plan_steps": self.plan_steps,
            "tool_results": self.tool_results[-20:],  # bound growth
            "open_files": self.open_files,
            "working_set": self.working_set,
            "introspection": self.introspection,
            "training_wheels": self.training_wheels,
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentState":
        s = cls(thread_id=str(data.get("thread_id") or ""))
        s.created = data.get("created") or s.created
        s.updated = data.get("updated") or s.updated
        s.objective = str(data.get("objective") or "")
        s.hypothesis = str(data.get("hypothesis") or "")
        s.root_cause = data.get("root_cause")
        s.last_critique = str(data.get("last_critique") or "")
        s.plan_steps = list(data.get("plan_steps") or [])
        s.tool_results = list(data.get("tool_results") or [])
        s.open_files = list(data.get("open_files") or [])
        s.working_set = list(data.get("working_set") or [])
        s.introspection = data.get("introspection")
        s.training_wheels = bool(data.get("training_wheels", True))
        s.meta = dict(data.get("meta") or {})
        return s

    def touch(self) -> None:
        self.updated = _now()

    def save(self) -> Path:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        path = STATE_DIR / f"{self.thread_id}.json"
        self.touch()
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        # Mirror latest for dashboard
        try:
            (ROOT / "artifacts" / "agent_state_latest.json").write_text(
                json.dumps(self.to_dict(), indent=2), encoding="utf-8"
            )
        except Exception:
            pass
        return path

    @classmethod
    def load(cls, thread_id: str) -> Optional["AgentState"]:
        path = STATE_DIR / f"{thread_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls.from_dict(data)
        except Exception:
            return None

    @classmethod
    def load_or_create(cls, thread_id: str = "") -> "AgentState":
        if thread_id:
            existing = cls.load(thread_id)
            if existing is not None:
                return existing
        return cls(thread_id=thread_id)


def latest_state() -> Optional[Dict[str, Any]]:
    path = ROOT / "artifacts" / "agent_state_latest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
