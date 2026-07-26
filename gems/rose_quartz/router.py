"""Rose Quartz — local-first router with optional Grok-class cloud burst."""

from __future__ import annotations

import json
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
        self.primary_model = primary_model or os.getenv("ETHER_PRIMARY_MODEL", "qwen2.5-coder:3b")
        self.fallback_model = os.getenv("ETHER_FALLBACK_MODEL", fallback_model)
        self.stream = os.getenv("ETHER_ROSE_STREAM", "0") == "1"
        self.client = httpx.Client(timeout=180.0)

    def execute(self, request: Envelope) -> ResponseEnvelope:
        if not isinstance(request.payload, RoseQuartzRequest):
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="rose-quartz",
                error=GemError(type=GemErrorType.UNKNOWN, message="Invalid payload", recoverable=False),
            )

        payload = request.payload
        force_burst = os.getenv("ETHER_FORCE_BURST", "0") == "1"
        if force_burst:
            burst_res = self._burst(request.task_id, payload)
            if burst_res is not None:
                return burst_res

        model = self.primary_model if payload.prefer_local else self.fallback_model

        try:
            return self._call(request.task_id, payload, model)
        except httpx.ConnectError:
            burst_res = self._burst(request.task_id, payload)
            if burst_res is not None:
                return burst_res
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="rose-quartz",
                error=GemError(
                    type=GemErrorType.DEPENDENCY,
                    message="Cannot connect to Ollama at " + self.ollama_base_url,
                    recoverable=True,
                    suggested_action="Start Ollama (`ollama serve`) and ensure OLLAMA_BASE_URL is correct",
                ),
            )
        except httpx.HTTPStatusError as e:
            body = e.response.text[:300]
            if e.response.status_code == 404 or "not found" in body.lower():
                msg = f"Model '{model}' not found in Ollama. Pull it or set ETHER_PRIMARY_MODEL."
            else:
                msg = f"Ollama HTTP {e.response.status_code}: {body}"
            if model != self.fallback_model:
                try:
                    return self._call(request.task_id, payload, self.fallback_model)
                except Exception:
                    pass
            burst_res = self._burst(request.task_id, payload)
            if burst_res is not None:
                return burst_res
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="rose-quartz",
                error=GemError(
                    type=GemErrorType.DEPENDENCY,
                    message=msg,
                    recoverable=True,
                    suggested_action=f"ollama pull {model}",
                ),
            )
        except Exception as e:
            if model != self.fallback_model:
                try:
                    return self._call(request.task_id, payload, self.fallback_model)
                except Exception:
                    pass
            burst_res = self._burst(request.task_id, payload)
            if burst_res is not None:
                return burst_res
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="rose-quartz",
                error=GemError(type=GemErrorType.RUNTIME, message=str(e), recoverable=True),
            )

    def _burst(self, task_id: UUID, payload: RoseQuartzRequest) -> ResponseEnvelope | None:
        try:
            from gems.rose_quartz.burst import burst_enabled, chat

            if not burst_enabled():
                return None
            messages = [{"role": m.role, "content": m.content or ""} for m in payload.messages]
            out = chat(messages, max_tokens=payload.max_tokens or 2048)
            if not out.get("ok"):
                return None
            return ResponseEnvelope(
                task_id=task_id,
                source_gem="rose-quartz",
                payload=RoseQuartzResponse(
                    content=out.get("content") or "",
                    model_used=str(out.get("model") or "burst"),
                    tokens=int((out.get("usage") or {}).get("total_tokens") or 0),
                    confidence_score=0.75,
                ),
            )
        except Exception:
            return None

    def _call(self, task_id: UUID, payload: RoseQuartzRequest, model: str) -> ResponseEnvelope:
        messages = [{"role": m.role, "content": m.content or ""} for m in payload.messages]
        body = {
            "model": model,
            "messages": messages,
            "stream": self.stream,
            "options": {"num_predict": payload.max_tokens},
        }
        if self.stream:
            return self._call_stream(task_id, body, model)
        response = self.client.post(f"{self.ollama_base_url}/api/chat", json=body)
        response.raise_for_status()
        data = response.json()
        content = data.get("message", {}).get("content", "")
        tokens = data.get("eval_count", 0) + data.get("prompt_eval_count", 0)
        return ResponseEnvelope(
            task_id=task_id,
            source_gem="rose-quartz",
            payload=RoseQuartzResponse(
                content=content, model_used=model, tokens=tokens, confidence_score=0.8
            ),
        )

    def _call_stream(self, task_id: UUID, body: dict, model: str) -> ResponseEnvelope:
        parts: list[str] = []
        tokens = 0
        with self.client.stream("POST", f"{self.ollama_base_url}/api/chat", json=body) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except Exception:
                    continue
                msg = chunk.get("message") or {}
                if msg.get("content"):
                    parts.append(msg["content"])
                tokens += int(chunk.get("eval_count") or 0)
                if chunk.get("done"):
                    break
        return ResponseEnvelope(
            task_id=task_id,
            source_gem="rose-quartz",
            payload=RoseQuartzResponse(
                content="".join(parts),
                model_used=model,
                tokens=tokens,
                confidence_score=0.8,
            ),
        )
