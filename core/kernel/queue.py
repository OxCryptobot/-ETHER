"""One FIFO. Dual pending dirs were a reliability defect."""
from __future__ import annotations
import os
from pathlib import Path

PENDING_DIR = "artifacts/jobs/pending"
DONE_DIR = "artifacts/jobs/done"
FAILED_DIR = "artifacts/jobs/failed"

def queue_root(root: Path | None = None) -> Path:
    base = Path(root or os.environ.get("ETHER_ROOT") or ".")
    path = base / PENDING_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path
