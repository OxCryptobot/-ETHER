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
            jobs.append((p, "fast", {}))
            continue
        jobs.append((p, job_class(job), job))

    has_non_live = any(c != LIVE for _, c, _ in jobs)
    if has_non_live:
        return [p for p, c, _ in jobs if c != LIVE]
    # All live — still drop denylisted fixtures if policy available
    return [p for p, c, job in jobs if c != LIVE or not _deny_live(job)]


def _deny_live(job: dict) -> bool:
    try:
        from core.live_fixture_policy import should_skip_live

        return bool(should_skip_live(job=job).get("skip"))
    except Exception:
        return False


def is_live_job(path: Path) -> bool:
    try:
        job = json.loads(path.read_text(encoding="utf-8"))
        return job_class(job) == LIVE
    except Exception:
        return False


def filter_live_denylist(paths: List[Path]) -> List[Path]:
    """Drop LIVE jobs matching timeout denylist; leave non-LIVE untouched."""
    out: List[Path] = []
    for p in paths:
        if not is_live_job(p):
            out.append(p)
            continue
        try:
            job = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            out.append(p)
            continue
        if _deny_live(job):
            continue
        out.append(p)
    return out
