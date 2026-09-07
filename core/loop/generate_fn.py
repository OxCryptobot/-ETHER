"""Rose generate adapter + agent-loop flag. Peeled off Pipeline."""
from __future__ import annotations

import os
from typing import Any, Callable
from uuid import UUID

from core.loop.gems_call import rose_complete
from core.schemas import RoseQuartzResponse


def agent_loop_enabled() -> bool:
    return os.getenv("ETHER_AGENT_LOOP", "0") == "1"


def make_generate_fn(pipe: Any, task_id: UUID, prefer_local: bool) -> Callable[..., str]:
    """Raw completion text; the loop does its own fence extraction."""

    def generate(prompt: str, temperature: float = 0.2, seed: int = 1) -> str:
        req, res = rose_complete(
            pipe.registry,
            task_id=task_id,
            prompt=prompt,
            prefer_local=prefer_local,
            temperature=temperature,
            seed=seed,
        )
        if res.error or not isinstance(res.payload, RoseQuartzResponse):
            raise RuntimeError(res.error.message if res.error else "no completion")
        return res.payload.content or ""

    return generate
