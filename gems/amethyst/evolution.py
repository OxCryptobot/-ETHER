"""Amethyst — interaction logging and future self-improvement."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from core.schemas import (
    Envelope,
    ResponseEnvelope,
    GemError,
    GemErrorType,
    AmethystRequest,
    AmethystResponse,
)


class Amethyst:
    """Phase 1: interaction logging only."""

    def __init__(self, log_dir: Path | None = None):
        self.log_dir = log_dir or Path("memory/interactions")
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def execute(self, request: Envelope) -> ResponseEnvelope:
        try:
            if isinstance(request.payload, AmethystRequest):
                action = request.payload.action
                interaction = request.payload.interaction
            else:
                data = request.payload.model_dump() if hasattr(request.payload, "model_dump") else {}
                action = data.get("action", "log")
                interaction = data.get("interaction", {})

            if action == "log":
                self._log(interaction)
                payload = AmethystResponse(status="logged")
            else:
                payload = AmethystResponse(status="not_implemented_yet")

            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="amethyst",
                payload=payload,
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
