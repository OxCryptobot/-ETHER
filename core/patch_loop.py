"""Multifile patch loop — apply unified diffs only under memory/scratch."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / "memory" / "scratch"


def extract_unified_diff(text: str) -> Optional[str]:
    if not text:
        return None
    if "diff --git" in text or re.search(r"^---\s+", text, re.M):
        # trim markdown fences
        t = text.strip()
        if t.startswith("```"):
            lines = t.split("\n")[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            t = "\n".join(lines)
        return t
    return None


def _safe_paths(diff: str) -> bool:
    """Only allow paths under memory/scratch."""
    for line in diff.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            # --- a/memory/scratch/foo.py
            if "/dev/null" in line:
                continue
            if "memory/scratch" not in line.replace("\\", "/"):
                return False
        if line.startswith("diff --git"):
            if "memory/scratch" not in line.replace("\\", "/"):
                return False
    return True


def apply_scratch_diff(diff: str) -> Dict[str, Any]:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    if not _safe_paths(diff):
        return {"ok": False, "error": "diff paths must stay under memory/scratch"}
    # write as file and git apply --directory if needed; fallback: manual not implemented
    p = subprocess.run(
        ["git", "apply", "--whitespace=nowarn", "-"],
        input=diff,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    return {
        "ok": p.returncode == 0,
        "returncode": p.returncode,
        "stderr": (p.stderr or "")[-500:],
        "stdout": (p.stdout or "")[-500:],
    }


def run_scratch_tests() -> Dict[str, Any]:
    """Run memory/scratch/test_*.py if present."""
    tests = sorted(SCRATCH.glob("test_*.py"))
    if not tests:
        # run any main modules with python -c import
        return {"ok": True, "detail": "no scratch tests"}
    results = []
    for t in tests[:5]:
        p = subprocess.run(
            ["python", str(t)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        results.append({"file": t.name, "ok": p.returncode == 0, "stderr": (p.stderr or "")[-200:]})
    ok = all(r["ok"] for r in results)
    return {"ok": ok, "results": results}


def maybe_patch_cycle(generated: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """If generated looks like a scratch-scoped diff, apply + test.

    Returns (report, code_for_sandbox).
    If not a diff, sandbox the original generated code.
    """
    diff = extract_unified_diff(generated)
    if not diff:
        return None, generated
    if not _safe_paths(diff):
        return {"ok": False, "error": "unsafe patch paths"}, generated
    applied = apply_scratch_diff(diff)
    if not applied.get("ok"):
        return applied, generated
    tested = run_scratch_tests()
    return {"apply": applied, "tests": tested, "ok": bool(tested.get("ok"))}, generated
