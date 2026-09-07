"""Persist a PipelineResult. Peeled off Pipeline._persist."""
from __future__ import annotations

from typing import Any

from core.spine.state_io import write_json


def persist_run(pipe: Any, result: Any) -> None:
    try:
        write_json(pipe.runs_dir / f"{result.task_id}.json", result.model_dump(mode="json"))
    except Exception as e:
        result.degraded.append(f"persist_failed:{type(e).__name__}")
