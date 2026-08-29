"""Typed improvement proposal — dual-window contract between ETHER and tutor.

Local 4B proposes. Grok tutor annotates. Host validates. Wheels stay ON.
Never applies a patch to core/ from the local model under training wheels.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

SCHEMA = "ether_improve_v1"
ALLOWED_WRITE_PREFIXES = (
    "artifacts/self_improve/",
    "memory/ether_apprentice/lessons/",
    "artifacts/jobs/pending/",
)
FORBIDDEN_WRITE_PREFIXES = (
    "core/",
    "scripts/",
    "dashboard/",
    "cli/",
    ".venv/",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_proposal(
    *,
    gap: str,
    hypothesis: str,
    metric: str,
    why: str,
    files: Optional[List[str]] = None,
    tests: Optional[List[str]] = None,
    patch_kind: str = "tool_or_lesson",
    source_kind: str = "fail_learn",
) -> Dict[str, Any]:
    return {
        "schema": SCHEMA,
        "id": f"imp_{uuid4().hex[:10]}",
        "created": _now(),
        "gap": (gap or "")[:300],
        "hypothesis": (hypothesis or "")[:400],
        "metric": (metric or "hard_live_pass")[:80],
        "why": (why or "")[:600],
        "files": list(files or []),
        "tests": list(tests or []),
        "patch_kind": patch_kind,
        "source_kind": source_kind,
        "status": "proposed",
        "training_wheels": True,
        "soft_launch": False,
        "apply_core": False,
        "tutor": "grok",
        "agent": "ether_4b",
    }


def write_allowed(rel: str) -> bool:
    path = (rel or "").replace("\\", "/").lstrip("/")
    if any(path.startswith(p) or path == p.rstrip("/") for p in FORBIDDEN_WRITE_PREFIXES):
        return False
    return any(path.startswith(p) for p in ALLOWED_WRITE_PREFIXES)


def persist(proposal: Dict[str, Any], root: Path) -> Path:
    out_dir = root / "artifacts" / "self_improve" / "proposals"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{proposal['id']}.json"
    path.write_text(json.dumps(proposal, indent=2), encoding="utf-8")
    latest = root / "artifacts" / "self_improve" / "latest.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps(proposal, indent=2), encoding="utf-8")
    return path
