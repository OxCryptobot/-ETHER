"""Named gem calls. Pipeline.run should not inline Envelope soup."""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
from uuid import UUID

from core.schemas import (
    BlackTourmalineRequest,
    ChatMessage,
    ClearQuartzRequest,
    Envelope,
    RoseQuartzRequest,
)


def sandbox_execute(
    registry: Any,
    *,
    task_id: UUID,
    generated: str,
    objective: str,
    timeout: int,
    files: Optional[Dict[str, str]] = None,
    prepare_code: bool = True,
    fixture_root: Optional[str] = None,
    orchestrator: Any = None,
) -> Tuple[Any, Any]:
    req = Envelope(
        task_id=task_id,
        target_gem="clear-quartz",
        payload=ClearQuartzRequest(
            code=generated or "",
            objective=objective,
            prepare_code=prepare_code,
            test_args=["tests"],
            files=dict(files or {}),
            fixture_root=fixture_root,
        ),
        timeout_seconds=timeout,
    )
    res = registry.execute(req)
    if orchestrator is not None:
        orchestrator.process_response(req, res)
    return req, res


def audit_execute(registry: Any, *, task_id: UUID, generated: str) -> Tuple[Any, Any]:
    req = Envelope(
        task_id=task_id,
        target_gem="black-tourmaline",
        payload=BlackTourmalineRequest(artifact=generated),
    )
    return req, registry.execute(req)


def rose_complete(
    registry: Any,
    *,
    task_id: UUID,
    prompt: str,
    prefer_local: bool,
    temperature: float = 0.2,
    seed: int = 1,
) -> Tuple[Any, Any]:
    req = Envelope(
        task_id=task_id,
        target_gem="rose-quartz",
        payload=RoseQuartzRequest(
            messages=[ChatMessage(role="user", content=prompt)],
            prefer_local=prefer_local,
            temperature=temperature,
            seed=seed,
        ),
    )
    return req, registry.execute(req)
