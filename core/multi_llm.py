"""Multi-LLM adapter — Ollama primary + Grok burst, latency-optimized.

OS-3 efficiency goals:
- One shared httpx.Client with keep-alive (no per-call TCP/TLS setup)
- Direct Ollama /api/chat for fast/live (skip Envelope/RoseQuartz alloc)
- Lane-specific timeouts and num_predict defaults
- warm() to pin model in VRAM before measurement jobs
- latency_ms on every response; publish() surfaces stats

Hardware lock: host never auto-pulls >4B.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "multi_llm.json"
STATS = ROOT / "artifacts" / "multi_llm_latency.json"

# Lane wall budgets (seconds)
TIMEOUT_FAST = float(os.getenv("ETHER_LLM_TIMEOUT_FAST", "90"))
TIMEOUT_LIVE = float(os.getenv("ETHER_LLM_TIMEOUT_LIVE", "300"))
TIMEOUT_BURST = float(os.getenv("ETHER_LLM_TIMEOUT_BURST", "120"))

# Sampling defaults tuned for code on ≤4B
DEFAULT_NUM_CTX = int(os.getenv("ETHER_NUM_CTX", "8192"))  # 32k was overkill for 4B latency
DEFAULT_TEMP = float(os.getenv("ETHER_TEMPERATURE", "0.2"))

_lock = threading.Lock()
_client: Optional[httpx.Client] = None
_model_cache: Optional[str] = None
_latency_samples: List[float] = []
_MAX_SAMPLES = 50


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base() -> str:
    return (os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")


def _get_client() -> httpx.Client:
    """Process-wide keep-alive client. Localhost → tiny pool, no proxy."""
    global _client
    if _client is not None:
        return _client
    with _lock:
        if _client is not None:
            return _client
        _client = httpx.Client(
            base_url=_base(),
            timeout=httpx.Timeout(TIMEOUT_LIVE, connect=5.0),
            limits=httpx.Limits(
                max_keepalive_connections=4,
                max_connections=8,
                keepalive_expiry=120.0,
            ),
            http2=False,  # Ollama is HTTP/1.1; avoid negotiation cost
            trust_env=False,  # never pick up HTTP_PROXY for localhost
        )
        return _client


def _primary_model() -> str:
    global _model_cache
    if _model_cache:
        return _model_cache
    env = (os.getenv("ETHER_PRIMARY_MODEL") or "").strip()
    if env:
        _model_cache = env
        return env
    try:
        from core.model_select import select_primary_model

        _model_cache = str(select_primary_model().get("model") or "qwen3.5:4b")
    except Exception:
        _model_cache = "qwen3.5:4b"
    return _model_cache


def _record_latency(ms: float) -> None:
    with _lock:
        _latency_samples.append(ms)
        if len(_latency_samples) > _MAX_SAMPLES:
            del _latency_samples[: len(_latency_samples) - _MAX_SAMPLES]


def _percentile(vals: List[float], p: float) -> Optional[float]:
    if not vals:
        return None
    s = sorted(vals)
    idx = min(len(s) - 1, max(0, int(round((p / 100.0) * (len(s) - 1)))))
    return round(s[idx], 1)


def _options(max_tokens: int, temperature: Optional[float]) -> Dict[str, Any]:
    temp = DEFAULT_TEMP if temperature is None else float(temperature)
    return {
        "num_predict": int(max_tokens),
        "temperature": temp,
        "top_p": float(os.getenv("ETHER_TOP_P", "0.9")),
        "top_k": int(os.getenv("ETHER_TOP_K", "40")),
        "presence_penalty": 0.0,
        "frequency_penalty": 0.0,
        "repeat_penalty": float(os.getenv("ETHER_REPEAT_PENALTY", "1.0")),
        "num_ctx": DEFAULT_NUM_CTX,
        "seed": int(os.getenv("ETHER_SEED", "1")),
    }


def lanes() -> Dict[str, Any]:
    primary = _primary_model()
    burst_on = os.getenv("ETHER_BURST", "0") == "1" and bool(
        os.getenv("ETHER_BURST_API_KEY") or os.getenv("XAI_API_KEY")
    )
    return {
        "updated": _now(),
        "fast": primary,
        "live": primary,
        "burst": os.getenv("ETHER_BURST_MODEL", "grok-3") if burst_on else None,
        "burst_enabled": burst_on,
        "timeouts_s": {"fast": TIMEOUT_FAST, "live": TIMEOUT_LIVE, "burst": TIMEOUT_BURST},
        "num_ctx": DEFAULT_NUM_CTX,
        "ollama_base": _base(),
        "keep_alive": True,
        "note": "Shared httpx keep-alive + direct Ollama path. Host ≤4B lock.",
    }


def warm(model: Optional[str] = None) -> Dict[str, Any]:
    """Pin model in VRAM with a 1-token generate. Call before measurement batches."""
    model = model or _primary_model()
    t0 = time.perf_counter()
    try:
        client = _get_client()
        r = client.post(
            "/api/generate",
            json={
                "model": model,
                "prompt": "ping",
                "stream": False,
                "keep_alive": "30m",
                "options": {"num_predict": 1, "temperature": 0.0, "num_ctx": 512},
            },
            timeout=60.0,
        )
        r.raise_for_status()
        ms = (time.perf_counter() - t0) * 1000
        _record_latency(ms)
        return {"ok": True, "model": model, "warm_ms": round(ms, 1)}
    except Exception as e:
        return {"ok": False, "model": model, "error": f"{type(e).__name__}: {e}"}


def chat(
    messages: List[Dict[str, str]],
    *,
    lane: str = "fast",
    max_tokens: int = 1024,
    temperature: Optional[float] = None,
) -> Dict[str, Any]:
    """Route a chat completion. Fast/live use direct Ollama; burst uses xAI."""
    lane = (lane or "fast").lower()
    t0 = time.perf_counter()

    if lane in ("burst", "cloud"):
        try:
            from gems.rose_quartz.burst import burst_enabled, chat as burst_chat

            if not burst_enabled():
                return {"ok": False, "error": "burst disabled or no API key", "lane": lane}
            out = burst_chat(messages, max_tokens=max_tokens)
            out["lane"] = lane
            out["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            if out.get("ok"):
                _record_latency(out["latency_ms"])
            return out
        except Exception as e:
            return {
                "ok": False,
                "error": f"{type(e).__name__}: {e}",
                "lane": lane,
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            }

    # Direct Ollama path — no Envelope / RoseQuartz allocation
    model = _primary_model()
    timeout = TIMEOUT_LIVE if lane == "live" else TIMEOUT_FAST
    # Cap tokens by lane: fast jobs should not run long generates
    if lane == "fast":
        max_tokens = min(int(max_tokens), 1024)
    body = {
        "model": model,
        "messages": [{"role": m.get("role", "user"), "content": m.get("content") or ""} for m in messages],
        "stream": False,
        "keep_alive": "30m",
        "options": _options(max_tokens, temperature),
        "think": os.getenv("ETHER_THINKING", "0") == "1",
    }
    try:
        client = _get_client()
        resp = client.post("/api/chat", json=body, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        content = (data.get("message") or {}).get("content") or ""
        tokens = int(data.get("eval_count") or 0) + int(data.get("prompt_eval_count") or 0)
        ms = (time.perf_counter() - t0) * 1000
        _record_latency(ms)
        if not content.strip():
            return {
                "ok": False,
                "error": f"Model {model} returned empty content",
                "lane": lane,
                "model": model,
                "latency_ms": round(ms, 1),
            }
        return {
            "ok": True,
            "content": content,
            "model": model,
            "tokens": tokens,
            "lane": lane,
            "latency_ms": round(ms, 1),
            "eval_count": int(data.get("eval_count") or 0),
            "prompt_eval_count": int(data.get("prompt_eval_count") or 0),
        }
    except httpx.TimeoutException:
        ms = (time.perf_counter() - t0) * 1000
        return {
            "ok": False,
            "error": f"timeout after {timeout}s",
            "lane": lane,
            "model": model,
            "latency_ms": round(ms, 1),
            "failure_type": "timeout",
        }
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        return {
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
            "lane": lane,
            "model": model,
            "latency_ms": round(ms, 1),
        }


def latency_stats() -> Dict[str, Any]:
    with _lock:
        samples = list(_latency_samples)
    return {
        "n": len(samples),
        "p50_ms": _percentile(samples, 50),
        "p95_ms": _percentile(samples, 95),
        "max_ms": round(max(samples), 1) if samples else None,
        "samples_tail": [round(x, 1) for x in samples[-10:]],
    }


def publish() -> Dict[str, Any]:
    payload = lanes()
    payload["latency"] = latency_stats()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    STATS.write_text(json.dumps(payload["latency"] | {"updated": _now()}, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "warm":
        print(json.dumps(warm(), indent=2))
    elif len(sys.argv) > 1 and sys.argv[1] == "bench":
        w = warm()
        print("warm", w)
        r = chat([{"role": "user", "content": "Reply with exactly: pong"}], lane="fast", max_tokens=8)
        print(json.dumps(r, indent=2))
        print(json.dumps(publish(), indent=2))
    else:
        print(json.dumps(publish(), indent=2))
