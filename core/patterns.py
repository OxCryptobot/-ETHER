"""Index and retrieve successful coding patterns via Citrine (Qdrant)."""

from __future__ import annotations

from typing import Any, Dict, List
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


def retrieve_pass_patterns(objective: str, k: int = 3) -> Dict[str, Any]:
    """Leak-safe retrieve from Citrine `patterns`.

    Same-task solutions are filtered out via prompt_guard.defines_target so
    vector memory cannot hand the model the answer on a held-out bench task.
    Never raises — offline Qdrant returns an empty block.
    """
    if not (objective or "").strip() or k <= 0:
        return {"block": "", "n": 0, "skipped": True}
    try:
        from core.registry import build_default_registry
        from core.schemas import CitrineRequest, Envelope

        res = build_default_registry().execute(
            Envelope(
                task_id=uuid4(),
                target_gem="citrine",
                payload=CitrineRequest(
                    action="search",
                    collection="patterns",
                    query=objective[:500],
                    top_k=max(k + 2, 5),
                ),
            )
        )
        if res.error:
            msg = res.error.message
            if is_optional_vector_offline(msg):
                return {"block": "", "n": 0, "skipped": True, "reason": "qdrant_offline"}
            return {"block": "", "n": 0, "error": msg[:200]}

        results = list(getattr(res.payload, "results", None) or [])
        try:
            from core.prompt_guard import defines_target

            safe: List[Any] = []
            for r in results:
                text = getattr(r, "text", "") or ""
                if defines_target(text, objective):
                    continue  # same-task solution — would contaminate eval
                safe.append(r)
            results = safe
        except Exception:
            # Cannot verify leak safety → serve nothing
            return {"block": "", "n": 0, "skipped": True, "reason": "guard_unavailable"}

        parts: List[str] = []
        for i, r in enumerate(results[:k], 1):
            score = getattr(r, "score", 0.0)
            text = (getattr(r, "text", "") or "")[:1200]
            if not text.strip():
                continue
            parts.append(f"### Citrine pattern {i} (score={score:.3f})\n{text}\n")
        block = "\n".join(parts)[:3000]
        return {"block": block, "n": len(parts)}
    except Exception as e:
        msg = str(e)[:200]
        if is_optional_vector_offline(msg):
            return {"block": "", "n": 0, "skipped": True, "reason": "qdrant_offline"}
        return {"block": "", "n": 0, "error": msg}
