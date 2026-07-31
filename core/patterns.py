"""Index successful coding patterns into Citrine (best-effort)."""

from __future__ import annotations

from typing import Any, Dict
from uuid import uuid4


def is_optional_vector_offline(error: str) -> bool:
    """True when Citrine/Qdrant is simply not running — product path must not fail.

    Local success-pattern files still work; vector index is optional infrastructure.
    """
    e = (error or "").lower()
    markers = (
        "10061",  # WinError connection refused
        "connection refused",
        "actively refused",
        "failed to establish",
        "connect call failed",
        "connection reset",
        "name or service not known",
        "nodename nor servname",
        "max retries exceeded",
        "qdrant",
        "httpconnectionpool",
    )
    return any(m in e for m in markers)


def index_pass_pattern(
    objective: str,
    code: str,
    confidence: float,
    strategy: str = "",
) -> Dict[str, Any]:
    """Store a PASS artifact in Citrine collection 'patterns'. Never raises."""
    try:
        from core.registry import build_default_registry
        from core.schemas import CitrineRequest, Envelope

        text = f"OBJECTIVE:\n{objective[:500]}\n\nCODE:\n{code[:3000]}"
        docs = [
            {
                "text": text,
                "metadata": {
                    "kind": "pass_pattern",
                    "confidence": confidence,
                    "strategy": strategy or "",
                },
            }
        ]
        res = build_default_registry().execute(
            Envelope(
                task_id=uuid4(),
                target_gem="citrine",
                payload=CitrineRequest(action="add", collection="patterns", documents=docs),
            )
        )
        if res.error:
            msg = res.error.message
            if is_optional_vector_offline(msg):
                return {"ok": True, "skipped": True, "reason": "qdrant_offline", "error": msg[:200]}
            return {"ok": False, "error": msg}
        return {"ok": True, "collection": "patterns"}
    except Exception as e:
        msg = str(e)[:200]
        if is_optional_vector_offline(msg):
            return {"ok": True, "skipped": True, "reason": "qdrant_offline", "error": msg}
        return {"ok": False, "error": msg}
