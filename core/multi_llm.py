"""Multi-LLM adapter — Ollama primary + Grok burst + lane routing.

Unified surface for the Operator Surface and host_agent.
Does not replace Rose Quartz; it orchestrates the existing pieces.

Lanes:
  fast   → host ≤4B Ollama (qwen3.5:4b family)
  live   → same host model under live_budget
  burst  → Grok / xAI when ETHER_BURST=1 and budget remains
  cloud  → explicit cloud request (still gated by burst budget)

Hardware lock preserved: host never auto-pulls >4B.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "multi_llm.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def lanes() -> Dict[str, Any]:
    """Current lane configuration."""
    from core.model_select import select_primary_model

    sel = select_primary_model()
    primary = sel.get("model") or os.getenv("ETHER_PRIMARY_MODEL", "qwen3.5:4b")
    burst_on = os.getenv("ETHER_BURST", "0") == "1" and bool(
        os.getenv("ETHER_BURST_API_KEY") or os.getenv("XAI_API_KEY")
    )
    return {
        "updated": _now(),
        "fast": primary,
        "live": primary,
        "burst": os.getenv("ETHER_BURST_MODEL", "grok-3") if burst_on else None,
        "burst_enabled": burst_on,
        "profile": sel.get("profile"),
        "available": sel.get("available") or [],
        "ollama_base": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        "note": "Host ≤4B lock. Burst is budget-gated and opt-in.",
    }


def chat(
    messages: List[Dict[str, str]],
    *,
    lane: str = "fast",
    max_tokens: int = 2048,
    temperature: Optional[float] = None,
) -> Dict[str, Any]:
    """Route a chat completion through the selected lane."""
    lane = (lane or "fast").lower()
    if lane in ("burst", "cloud"):
        try:
            from gems.rose_quartz.burst import burst_enabled, chat as burst_chat

            if not burst_enabled():
                return {"ok": False, "error": "burst disabled or no API key", "lane": lane}
            out = burst_chat(messages, max_tokens=max_tokens)
            out["lane"] = lane
            return out
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}", "lane": lane}

    # Local Ollama via Rose Quartz
    try:
        from core.schemas import Envelope, RoseQuartzRequest, Message
        from gems.rose_quartz.router import RoseQuartz
        from uuid import uuid4

        rq = RoseQuartz()
        payload = RoseQuartzRequest(
            messages=[Message(role=m["role"], content=m.get("content") or "") for m in messages],
            max_tokens=max_tokens,
            prefer_local=True,
        )
        if temperature is not None:
            try:
                payload.temperature = float(temperature)
            except Exception:
                pass
        env = Envelope(task_id=uuid4(), source_gem="multi-llm", payload=payload)
        resp = rq.execute(env)
        if resp.error:
            return {
                "ok": False,
                "error": resp.error.message,
                "lane": lane,
                "model": None,
            }
        p = resp.payload
        return {
            "ok": True,
            "content": getattr(p, "content", "") or "",
            "model": getattr(p, "model_used", ""),
            "tokens": getattr(p, "tokens", 0),
            "lane": lane,
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "lane": lane}


def publish() -> Dict[str, Any]:
    payload = lanes()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(publish(), indent=2))
