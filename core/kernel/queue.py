"""One FIFO. Dual pending dirs were a reliability defect."""
from __future__ import annotations
import os, shutil
from pathlib import Path

PENDING_DIR = "artifacts/jobs/pending"
DONE_DIR = "artifacts/jobs/done"
FAILED_DIR = "artifacts/jobs/failed"
LEGACY = ("artifacts/pending", "pending")

def queue_root(root: Path | None = None) -> Path:
    base = Path(root or os.environ.get("ETHER_ROOT") or ".")
    path = base / PENDING_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path

def collapse_legacy(root: Path | None = None) -> int:
    base = Path(root or os.environ.get("ETHER_ROOT") or ".")
    dest = queue_root(base)
    moved = 0
    for rel in LEGACY:
        src = base / rel
        if not src.is_dir():
            continue
        for p in src.glob("*.json"):
            target = dest / p.name
            if not target.exists():
                shutil.move(str(p), str(target))
                moved += 1
    return moved
