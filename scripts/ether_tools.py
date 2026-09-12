"""Allowlisted workspace tools for the ETHER desktop app."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]


def list_tree(limit: int = 80) -> List[str]:
    rows: List[str] = []
    for sub in ("core", "gems", "scripts", "tests"):
        d = ROOT / sub
        if not d.is_dir():
            continue
        for p in sorted(d.rglob("*.py")):
            rows.append(str(p.relative_to(ROOT)))
            if len(rows) >= limit:
                return rows
    return rows


def run_allowlisted(kind: str, cwd: Path | None = None) -> Dict[str, Any]:
    root = cwd or ROOT
    table = {
        "pytest-fast": [ "python3", "-m", "pytest", "tests/test_agentic.py", "tests/test_gem_topo.py", "-q", "--tb=line" ],
        "git-status": [ "git", "status", "-sb" ],
        "git-log": [ "git", "log", "-1", "--oneline" ],
    }
    argv = table.get(kind)
    if not argv:
        return {"ok": False, "error": "denied", "kind": kind}
    try:
        proc = subprocess.run(argv, cwd=str(root), capture_output=True, text=True, timeout=90)
        return {
            "ok": proc.returncode == 0,
            "kind": kind,
            "tail": ((proc.stdout or "") + (proc.stderr or ""))[-1500:],
        }
    except Exception as exc:
        return {"ok": False, "kind": kind, "error": type(exc).__name__}
