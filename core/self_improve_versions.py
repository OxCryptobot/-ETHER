"""Versioned snapshots for self-improve artifacts. Rollback is file-level.

Does not snapshot core/. Tutor-gated core changes live in git history.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
SNAP = ROOT / "artifacts" / "self_improve" / "versions"


def snapshot(proposal_id: str, src: Path) -> Optional[Path]:
    if not src.exists() or not src.is_file():
        return None
    dest_dir = SNAP / proposal_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = dest_dir / f"{stamp}_{src.name}"
    shutil.copy2(src, dest)
    index = dest_dir / "index.json"
    rows: list = []
    if index.exists():
        try:
            rows = json.loads(index.read_text(encoding="utf-8"))
        except Exception:
            rows = []
    if not isinstance(rows, list):
        rows = []
    rows.append({"ts": stamp, "file": dest.name, "src": str(src)})
    index.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return dest


def latest(proposal_id: str) -> Optional[Path]:
    dest_dir = SNAP / proposal_id
    if not dest_dir.exists():
        return None
    files = sorted(dest_dir.glob("*.json"))
    files = [p for p in files if p.name != "index.json"]
    return files[-1] if files else None


def rollback(proposal_id: str, dest: Path) -> Dict[str, Any]:
    src = latest(proposal_id)
    if src is None:
        return {"ok": False, "error": "no_snapshot"}
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return {"ok": True, "restored_from": str(src), "dest": str(dest)}
