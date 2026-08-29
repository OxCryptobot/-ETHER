"""Dual-window protocol helpers on top of chat_bus.

Agent → tutor: type=learn proposal
Tutor → agent: type=critique_reply | agent_reply with annotated patch notes
Clarify: type=critique_request before any core commit
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.chat_bus import envelope, receive, send


def submit_proposal(proposal: Dict[str, Any]) -> Dict[str, Any]:
    env = envelope(
        from_actor="ether",
        type_="learn",
        payload={
            "text": (
                f"PROPOSAL {proposal.get('id')}\n"
                f"gap: {proposal.get('gap')}\n"
                f"hypothesis: {proposal.get('hypothesis')}\n"
                f"metric: {proposal.get('metric')}\n"
                f"why: {proposal.get('why')}\n"
                "Reply with accept|revise|reject and annotated patch notes. Wheels stay ON."
            )[:2000],
            "proposal_id": proposal.get("id"),
            "gap": proposal.get("gap"),
            "metric": proposal.get("metric"),
        },
        job_id=str(proposal.get("id") or ""),
        requires_reply=True,
    )
    path = send(env, to_grok=True)
    return {"ok": True, "envelope_id": env["id"], "path": str(path), "direction": "agent_to_tutor"}


def ask_clarify(proposal_id: str, question: str) -> Dict[str, Any]:
    env = envelope(
        from_actor="ether",
        type_="critique_request",
        payload={"text": question[:1500], "proposal_id": proposal_id},
        job_id=proposal_id,
        requires_reply=True,
    )
    path = send(env, to_grok=True)
    return {"ok": True, "envelope_id": env["id"], "path": str(path), "direction": "clarify"}


def ingest_tutor(*, limit: int = 10) -> List[Dict[str, Any]]:
    items = receive(from_grok=True, limit=limit)
    out = []
    for env in items:
        if env.get("type") not in {"critique_reply", "agent_reply", "plan", "learn"}:
            continue
        payload = env.get("payload") or {}
        out.append(
            {
                "id": env.get("id"),
                "type": env.get("type"),
                "text": str(payload.get("text") or "")[:1500],
                "proposal_id": payload.get("proposal_id"),
                "from": env.get("from"),
            }
        )
    return out
