"""Pipeline.run start/resume/gems. Strangler slice off the 76kB god-file."""
from __future__ import annotations

import os
from typing import Any, Callable, Set


def start_resume_gems(
    result: Any,
    tid: str,
    objective: str,
    strategy: str,
    write_progress: Callable[..., None],
) -> Set[str]:
    write_progress(tid, objective, "start", strategy=strategy)
    skip: Set[str] = set()
    try:
        from core.checkpoint import resume_if_any
        from core.loop.resume import skipped_stages

        prior = resume_if_any(os.getenv("ETHER_RESUME_RUN_ID") or "")
        if prior is not None:
            skip = set(skipped_stages(prior))
            write_progress(
                tid,
                objective,
                "resume",
                detail=f"{getattr(prior, 'stage', 'loaded')} skip={sorted(skip)}",
            )
    except Exception as exc:
        result.degraded.append(f"resume:{type(exc).__name__}")

    if "gems" in skip:
        write_progress(tid, objective, "gems", detail="skipped_resume")
        return skip
    try:
        from core.loop.gem_step import annotate_all

        gem_trace = annotate_all()
        write_progress(
            tid,
            objective,
            "gems",
            detail=",".join(f"{row['stage']}:{row['gem']}" for row in gem_trace),
        )
    except Exception as exc:
        result.degraded.append(f"gem_protocol:{type(exc).__name__}")
    return skip
