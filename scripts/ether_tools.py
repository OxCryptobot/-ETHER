"""Allowlisted workspace tools for the ETHER desktop app."""
from __future__ import annotations

import os

import subprocess
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()


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


def apply_replace(rel: str, old: str, new: str, root: Path | None = None) -> Dict[str, Any]:
    base = root or ROOT
    target = (base / rel).resolve()
    target.relative_to(base.resolve())
    txt = target.read_text(encoding="utf-8")
    if old not in txt:
        return {"ok": False, "error": "not_found", "path": rel}
    target.write_text(txt.replace(old, new, 1), encoding="utf-8")
    return {"ok": True, "path": rel}


def search(q: str, limit: int = 30, root: Path | None = None) -> List[str]:
    base = root or ROOT
    needle = (q or "").lower()
    hits: List[str] = []
    if not needle:
        return hits
    for p in base.rglob("*.py"):
        if any(part.startswith(".") for part in p.parts):
            continue
        try:
            if needle in p.read_text(encoding="utf-8", errors="ignore").lower():
                hits.append(str(p.relative_to(base)))
        except Exception:
            continue
        if len(hits) >= limit:
            break
    return hits


def preview_replace(rel: str, old: str, new: str, root: Path | None = None) -> Dict[str, Any]:
    base = root or ROOT
    target = (base / rel).resolve()
    txt = target.read_text(encoding="utf-8")
    return {"ok": old in txt, "path": rel, "diff": f"- {old}\n+ {new}"}
