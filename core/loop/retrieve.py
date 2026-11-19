"""Repo-map / context retrieval peeled off Pipeline."""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

from core.context import context_enabled, gather_workspace_context

REPO_SIGNALS = re.compile(
    r"\b(this repo|this codebase|this project|existing|refactor|the file|"
    r"our |src/|core/|gems/|scripts/|tests/|\.py\b|module\b|package\b|"
    r"import from|update the|modify the|fix the bug in)\b",
    re.IGNORECASE,
)


def needs_repo_context(objective: str) -> bool:
    if os.getenv("ETHER_FORCE_CONTEXT", "0") == "1":
        return True
    return bool(REPO_SIGNALS.search(objective or ""))


def fetch_repo_map(result: Any) -> str:
    from core.pipeline import StageResult

    t = time.perf_counter()
    text = ""
    detail = ""
    try:
        from gems.grandidierite.registry import run_tool

        rm = run_tool("repo_map", {"max_files": 40})
        if rm.get("ok"):
            files = (rm.get("files") or [])[:15]
            lines = [f["path"] + ": " + ", ".join(f.get("symbols") or []) for f in files]
            text = "\n".join(lines)[:2500]
        else:
            detail = str(rm.get("error") or "repo_map unavailable")[:120]
    except Exception as e:
        detail = str(e)[:120]
    result.stages.append(
        StageResult(
            stage="repo_map",
            success=bool(text),
            detail=detail or f"{len(text)} chars",
            duration_ms=(time.perf_counter() - t) * 1000,
        )
    )
    return text


def fetch_context(result: Any, objective: str) -> str:
    from core.pipeline import StageResult

    if not context_enabled():
        return ""
    if not needs_repo_context(objective):
        result.stages.append(
            StageResult(
                stage="context",
                success=True,
                detail="skipped — self-contained objective",
            )
        )
        return ""
    t = time.perf_counter()
    try:
        block = gather_workspace_context(Path.cwd(), query=objective)
        result.stages.append(
            StageResult(
                stage="context",
                success=True,
                detail=f"{len(block)} chars",
                duration_ms=(time.perf_counter() - t) * 1000,
            )
        )
        return block
    except Exception as e:
        result.stages.append(
            StageResult(
                stage="context",
                success=False,
                detail=str(e)[:120],
                duration_ms=(time.perf_counter() - t) * 1000,
            )
        )
        return ""
