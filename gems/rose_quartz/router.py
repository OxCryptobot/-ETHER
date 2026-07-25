"""Rose Quartz — local-first inference router."""

from __future__ import annotations

import os
from uuid import UUID

import httpx

from core.schemas import (
    Envelope,
    ResponseEnvelope,
    RoseQuartzRequest,
    RoseQuartzResponse,
    GemError,
    GemErrorType,
)


class RoseQuartz:
    def __init__(
        self,
        ollama_base_url: str | None = None,
        primary_model: str | None = None,
        fallback_model: str = "deepseek-r1:8b",
    ):
        self.ollama_base_url = (ollama_base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.primary_model = primary_model or os.getenv("ETHER_PRIMARY_MODEL", "qwen3-coder-next:32b-q4_k_m")
        self.fallback_model = fallback_model
        self.client = httpx.Client(timeout=120.0)

    def execute(self, request: Envelope) -> ResponseEnvelope:
        if not isinstance(request.payload, RoseQuartzRequest):
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="rose-quartz",
                error=GemError(type=GemErrorType.UNKNOWN, message="Invalid payload", recoverable=False),
            )

        payload = request.payload
        model = self.primary_model if payload.prefer_local else self.fallback_model

        try:
            return self._call(request.task_id, payload, model)
        except httpx.ConnectError:
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="rose-quartz",
                error=GemError(
                    type=GemErrorType.DEPENDENCY,
                    message="Cannot connect to Ollama",
                    recoverable=True,
                    suggested_action="Start Ollama: ollama serve",
                ),
            )
        except Exception as e:
            # try fallback once
            if model != self.fallback_model:
                try:
                    return self._call(request.task_id, payload, self.fallback_model)
                except Exception:
                    pass
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="rose-quartz",
                error=GemError(type=GemErrorType.RUNTIME, message=str(e), recoverable=True),
            )

    def _call(self, task_id: UUID, payload: RoseQuartzRequest, model: str) -> ResponseEnvelope:
        messages = [{"role": m.role, "content": m.content or ""} for m in payload.messages]
        response = self.client.post(
            f"{self.ollama_base_url}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {"num_predict": payload.max_tokens},
            },
        )
        response.raise_for_status()
        data = response.json()
        content = data.get("message", {}).get("content", "")
        tokens = data.get("eval_count", 0) + data.get("prompt_eval_count", 0)
        return ResponseEnvelope(
            task_id=task_id,
            source_gem="rose-quartz",
            payload=RoseQuartzResponse(content=content, model_used=model, tokens=tokens, confidence_score=0.8),
        )
