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


def _envf(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except (TypeError, ValueError):
        return default


def _envi(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except (TypeError, ValueError):
        return default


def decode_options(
    max_tokens: int,
    temperature: float | None = None,
    seed: int | None = None,
) -> dict:
    """Sampling parameters for the local model.

    This used to send only `num_predict`, so Ollama applied the Modelfile
    defaults. For qwen3.6:35b-a3b those are temperature=1.0, top_p=0.95,
    top_k=20 and — the damaging one — **presence_penalty=1.5**.

    A presence penalty penalises re-emitting tokens already in context. Correct
    code MUST repeat identifiers, keywords and punctuation, so that setting
    pushes the model away from valid syntax in proportion to how much it has
    already written. It is close to a worst-case sampling configuration for
    code generation, and it was in force for every run this project has ever
    made.

    A seed is set so runs are reproducible: without one, a regression cannot be
    distinguished from sampling noise, which makes the guardian ratchet and any
    ablation meaningless.

    Every value is overridable, because best-of-N sampling wants a HIGHER
    temperature (diversity to select from) while single-shot wants a low one.
    """
    return {
        "num_predict": max_tokens,
        # Per-request override wins; the env value is the default.
        "temperature": _envf("ETHER_TEMPERATURE", 0.2) if temperature is None else float(temperature),
        "top_p": _envf("ETHER_TOP_P", 0.9),
        "top_k": _envi("ETHER_TOP_K", 40),
        # Explicitly neutralise the two penalties. Repetition is correct in code.
        "presence_penalty": _envf("ETHER_PRESENCE_PENALTY", 0.0),
        "frequency_penalty": _envf("ETHER_FREQUENCY_PENALTY", 0.0),
        "repeat_penalty": _envf("ETHER_REPEAT_PENALTY", 1.0),
        # The composite prompt has been measured at ~6.9k chars; the Ollama
        # default context is far smaller, so prompts were being silently
        # truncated — from the front, which is where the objective lives.
        "num_ctx": _envi("ETHER_NUM_CTX", 4096),
        "seed": _envi("ETHER_SEED", 1) if seed is None else int(seed),
    }


def thinking_enabled() -> bool:
    """Whether to let a reasoning model emit thinking tokens.

    qwen3.6 advertises a `thinking` capability, and reasoning tokens count
    against `num_predict`. With the previous 4096-token budget the model spent
    its entire allowance reasoning and returned EMPTY CONTENT on hard tasks.
    Measured over a 360-sample ablation: 214 samples (59%) failed — 147 timed
    out and 64 returned nothing — and because errors count as fails, the
    experiment measured infrastructure failure rather than code quality.

    Disabled by default for code generation: the same prompt that produced an
    empty completion after thousands of reasoning tokens returns correct code
    in ~18 tokens with `think=false`. Whether reasoning improves code quality
    when given an adequate budget is a real question — but it is an experiment
    to run deliberately, not a default to stumble into.
    """
    return os.getenv("ETHER_THINKING", "0") == "1"


class RoseQuartz:
    def __init__(
        self,
        ollama_base_url: str | None = None,
        primary_model: str | None = None,
        fallback_model: str = "",
    ):
        self.ollama_base_url = (ollama_base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        try:
            from core.model_select import resolved_fallback, resolved_primary

            self.primary_model = resolved_primary(primary_model)
            self.fallback_model = resolved_fallback(fallback_model or os.getenv("ETHER_FALLBACK_MODEL") or "")
        except Exception:
            self.primary_model = primary_model or os.getenv("ETHER_PRIMARY_MODEL", "qwen3.5:4b")
            fb = os.getenv("ETHER_FALLBACK_MODEL", "").strip()
            self.fallback_model = fb or self.primary_model
        self.stream = os.getenv("ETHER_ROSE_STREAM", "0") == "1"
        self.client = httpx.Client(timeout=_envf("ETHER_HTTP_TIMEOUT", 600.0))

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
            "options": decode_options(
                payload.max_tokens,
                getattr(payload, "temperature", None),
                getattr(payload, "seed", None),
            ),
            # Reasoning tokens count against num_predict; leaving this on with a
            # small budget produced empty completions on 64 of 360 samples.
            "think": thinking_enabled(),
        }
        if self.stream:
            return self._call_stream(task_id, body, model)
        response = self.client.post(f"{self.ollama_base_url}/api/chat", json=body)
        response.raise_for_status()
        data = response.json()
        content = data.get("message", {}).get("content", "")
        tokens = data.get("eval_count", 0) + data.get("prompt_eval_count", 0)
        # An HTTP 200 carrying empty content is a failed generation, not a
        # successful one. It used to return a success envelope, the harness
        # then appended `print('ok')` to the empty string, the sandbox exited
        # 0, and the run was recorded `status=complete` with a positive reward
        # — the model produced nothing and the bandit learned from it.
        # Observed live: bench task b15 scored conf=0.650 this way, caught
        # only because held-out grading reported "no generated code".
        if not content.strip():
            return ResponseEnvelope(
                task_id=task_id,
                source_gem="rose-quartz",
                error=GemError(
                    type=GemErrorType.RUNTIME,
                    message=f"Model {model} returned empty content",
                    recoverable=True,
                    suggested_action="Retry, or check the model is loaded and the prompt is not over its context limit",
                ),
            )
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
