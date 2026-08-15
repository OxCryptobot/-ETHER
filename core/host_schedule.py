"""Host scheduling helpers — FAST-first hard gate + train-wheels LIVE block."""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

from core.job_class import job_class, LIVE, FAST, MEASURE, RECOVERY


def filter_fast_first(paths: List[Path]) -> List[Path]:
    """Moonshot 13: never surface LIVE while any FAST/MEASURE/RECOVERY pending."""
    jobs = []
    for p in paths:
        try:
            job = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            jobs.append((p, "fast"))
            continue
        jobs.append((p, job_class(job)))

    has_blocking = any(c in (FAST, MEASURE, RECOVERY, "any") for _, c in jobs if c != LIVE)
    # also treat unknown as blocking relative to live
    has_non_live = any(c != LIVE for _, c in jobs)
    if has_non_live:
        return [p for p, c in jobs if c != LIVE]
    return [p for p, _ in jobs]


def is_live_job(path: Path) -> bool:
    try:
        job = json.loads(path.read_text(encoding="utf-8"))
        return job_class(job) == LIVE
    except Exception:
        return False
