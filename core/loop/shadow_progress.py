"""Checkpoint-shadowed write_progress. Peeled off Pipeline.run (I-010)."""
from __future__ import annotations

from typing import Any, Callable


def make_write_progress(result: Any) -> Callable[..., None]:
    from core.progress import write_progress as _write_progress

    def write_progress(
        task_id: str, objective: str, stage: str, detail: str = "", **extra: Any
    ) -> None:
        _write_progress(task_id, objective, stage, detail, **extra)
        try:
            from core.checkpoint import checkpoint_pipeline

            payload = {"strategy": result.strategy}
            if detail:
                payload["detail"] = str(detail)[:120]
            for key, val in extra.items():
                payload[str(key)[:40]] = str(val)[:80]
            checkpoint_pipeline(
                run_id=str(task_id),
                stage=stage,
                objective=objective,
                n_stages=len(result.stages),
                extra=payload,
            )
        except Exception:
            pass

    return write_progress
