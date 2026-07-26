"""Index successful coding patterns into Citrine (best-effort)."""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import uuid4


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
            return {"ok": False, "error": res.error.message}
        return {"ok": True, "collection": "patterns"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
