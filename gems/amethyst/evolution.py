"""Amethyst — logging + online learning (bandit policy)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from core.learning import BanditPolicy, append_experience, compute_reward, learning_enabled
from core.schemas import (
    Envelope,
    ResponseEnvelope,
    GemError,
    GemErrorType,
    AmethystRequest,
    AmethystResponse,
)


class Amethyst:
    """Phase 1 was logs only. Phase 2: reward + bandit updates."""

    def __init__(self, log_dir: Path | None = None):
        self.log_dir = log_dir or Path("memory/interactions")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.policy = BanditPolicy()

    def execute(self, request: Envelope) -> ResponseEnvelope:
        try:
            if isinstance(request.payload, AmethystRequest):
                action = request.payload.action
                interaction = request.payload.interaction or {}
            else:
                data = request.payload.model_dump() if hasattr(request.payload, "model_dump") else {}
                action = data.get("action", "log")
                interaction = data.get("interaction") or {}

            if action == "log":
                self._log(interaction)
                # optional learn from the same payload
                if learning_enabled() and interaction.get("learn"):
                    self._learn(interaction)
                payload = AmethystResponse(status="logged")
            elif action == "recommend":
                arm = self.policy.select() if learning_enabled() else "default"
                payload = AmethystResponse(status=f"strategy:{arm}")
            elif action == "stats":
                payload = AmethystResponse(status=json.dumps(self.policy.snapshot()))
            else:
                payload = AmethystResponse(status="unknown_action")

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

    def _learn(self, interaction: Dict[str, Any]) -> None:
        strategy = str(interaction.get("strategy") or "default")
        reward = interaction.get("reward")
        if reward is None:
            reward = compute_reward(
                exit_code=interaction.get("exit_code"),
                confidence=float(interaction.get("confidence") or 0.0),
                audit_approved=bool(interaction.get("audit_approved")),
                retries=int(interaction.get("retries") or 0),
            )
        self.policy.update(strategy, float(reward))
        append_experience(
            {
                "strategy": strategy,
                "reward": reward,
                "objective": interaction.get("objective"),
                "confidence": interaction.get("confidence"),
                "exit_code": interaction.get("exit_code"),
                "audit_approved": interaction.get("audit_approved"),
                "status": interaction.get("status"),
            }
        )
