"""Resume-skip detail for Pipeline.write_progress. Strangler helper."""
from __future__ import annotations

from typing import Set


def skip_detail(skip: Set[str], stage: str) -> str:
    return "skipped_resume" if stage in skip else ""
