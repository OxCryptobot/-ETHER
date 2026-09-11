"""Stream tool observations onto Dual chat outbox. Chrome unchanged."""
from __future__ import annotations

from typing import Any, Dict

from core.chat_bus import envelope, send


def stream_observation(tool: str, observation: Dict[str, Any], *, job_id: str = "") -> Dict[str, Any]:
    text = f"{tool}: {str(observation)[:280]}"
    env = envelope(
        from_actor="ether",
        type_="status",
        payload={"text": text, "tool": tool, "observation": observation},
        job_id=job_id or None,
        requires_reply=False,
    )
    path = send(env, to_grok=True)
    return {"ok": True, "id": env["id"], "path": str(path), "lane": "outbox"}
