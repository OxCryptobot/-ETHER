"""Rose Quartz — local-first inference router."""

from __future__ import annotations

import json
from typing import List, Optional
from uuid import UUID

import httpx

from core.schemas import (
    Envelope,
    ResponseEnvelope,
    RoseQuartzRequest,
    RoseQuartzResponse,
    ChatMessage,
    GemError,
    GemErrorType,
)


class RoseQuartz:
    """Routes requests to the best available local (or cloud) model."""

    def __init__(
        self,
        ollama_base_url: str = "http://localhost:11434",
        primary_model: str = "qwen3-coder-next:32b-q4_k_m",
        fallback_model: str = "deepseek-r1:8b",
    ):
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.primary_model = primary_model
        self.fallback_model = fallback_model
        self.client = httpx.Client(timeout=120.0)

    def execute(self, request: Envelope) -> ResponseEnvelope:
        if not isinstance(request.payload, RoseQuartzRequest):
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="rose-quartz",
                error=GemError(
                    type=GemErrorType.UNKNOWN,
                    message="Invalid payload type for Rose Quartz",
                    recoverable=False,
                ),
            )

        payload: RoseQuartzRequest = request.payload

        try:
            # Prefer local primary model
            model = self.primary_model if payload.prefer_local else self.fallback_model

            messages = [
                {"role": m.role, "content": m.content or ""}
                for m in payload.messages
            ]

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
                task_id=request.task_id,
                source_gem="rose-quartz",
                payload=RoseQuartzResponse(
                    content=content,
                    model_used=model,
                    tokens=tokens,
                    confidence_score=0.85,  # placeholder — will be improved later
                ),
            )

        except httpx.ConnectError:
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="rose-quartz",
                error=GemError(
                    type=GemErrorType.DEPENDENCY,
                    message="Cannot connect to Ollama. Is it running on localhost:11434?",
                    recoverable=True,
                    suggested_action="Start Ollama with: ollama serve",
                ),
            )
        except httpx.HTTPStatusError as e:
            # Try fallback model once
            if model == self.primary_model:
                try:
                    return self._call_model(request.task_id, payload, self.fallback_model)
                except Exception:
                    pass

            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="rose-quartz",
                error=GemError(
                    type=GemErrorType.RUNTIME,
                    message=f"Ollama error: {e.response.status_code} - {e.response.text[:200]}",
                    recoverable=True,
                ),
            )
        except Exception as e:
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="rose-quartz",
                error=GemError(
                    type=GemErrorType.UNKNOWN,
                    message=str(e),
                    recoverable=True,
                ),
            )

    def _call_model(
        self, task_id: UUID, payload: RoseQuartzRequest, model: str
    ) -> ResponseEnvelope:
        messages = [
            {"role": m.role, "content": m.content or ""}
            for m in payload.messages
        ]

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
            payload=RoseQuartzResponse(
                content=content,
                model_used=model,
                tokens=tokens,
                confidence_score=0.75,
            ),
        )
