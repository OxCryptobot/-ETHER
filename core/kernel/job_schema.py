"""Pending job schema. Invalid envelopes never enter the FIFO."""
from __future__ import annotations
from typing import Any, Dict, List, Tuple

ALLOWED_CLASS = frozenset({"fast", "live", "measure", "gate_sample", "ops"})
REQUIRED = ("id", "steps")


def validate_job(job: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    if not isinstance(job, dict):
        return False, ["not_object"]
    for key in REQUIRED:
        if key not in job:
            errors.append(f"missing:{key}")
    jid = str(job.get("id") or "")
    if not jid or any(c in jid for c in "/\\"):
        errors.append("bad_id")
    klass = str(job.get("class") or "fast")
    if klass not in ALLOWED_CLASS:
        errors.append("bad_class")
    steps = job.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("steps_empty")
    else:
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                errors.append(f"step_{i}_not_object")
                continue
            argv = step.get("argv")
            if not isinstance(argv, list) or not argv:
                errors.append(f"step_{i}_argv")
            timeout = step.get("timeout", 120)
            try:
                if int(timeout) <= 0 or int(timeout) > 3600:
                    errors.append(f"step_{i}_timeout")
            except (TypeError, ValueError):
                errors.append(f"step_{i}_timeout")
    return (len(errors) == 0), errors
