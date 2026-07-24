"""Amethyst — interaction logging and future self-improvement."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from core.schemas import Envelope, ResponseEnvelope, GemError, GemErrorType


class AmethystRequest(BaseModel):
    action: str = "log"  # log | analyze | recommend
    interaction: Dict[str, Any] = Field(default_factory=dict)


class AmethystResponse(BaseModel):
    status: str
    recommendation: Optional[str] = None


class Amethyst:
    """Phase 1: interaction logging only. LoRA comes later."""

    def __init__(self, log_dir: Path | None = None):
        self.log_dir = log_dir or Path("memory/interactions")
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def execute(self, request: Envelope) -> ResponseEnvelope:
        try:
            data = request.payload.model_dump() if hasattr(request.payload, "model_dump") else {}
            action = data.get("action", "log")

            if action == "log":
                self._log(data.get("interaction", {}))
                payload = AmethystResponse(status="logged")
            else:
                payload = AmethystResponse(status="not_implemented_yet")

            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="amethyst",
                payload=payload,  # type: ignore
            )
        except Exception as e:
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="amethyst",
                error=GemError(type=GemErrorType.RUNTIME, message=str(e), recoverable=True),
            )

    def _log(self, interaction: Dict[str, Any]) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        entry = {"timestamp": ts, **interaction}
        log_file = self.log_dir / f"{ts[:10]}.jsonl"
        with log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
