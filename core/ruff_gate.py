"""Phase 1 — optional ruff check on staged code (fail-closed when enabled)."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


def ruff_gate_enabled() -> bool:
    return (os.getenv("ETHER_RUFF_GATE") or "").strip() == "1"


def run_ruff(paths: List[Path], *, cwd: Optional[Path] = None) -> Dict[str, Any]:
    """Run ruff check on paths. Returns ok/score/stdout. Missing ruff = skip unless forced."""
    if not paths:
        return {"ok": True, "skipped": True, "reason": "no paths"}
    exe = shutil.which("ruff")
    if exe is None:
        # try python -m ruff
        cmd = ["python", "-m", "ruff", "check", "--output-format", "text"]
    else:
        cmd = [exe, "check", "--output-format", "text"]
    cmd.extend(str(p) for p in paths)
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except FileNotFoundError:
        if ruff_gate_enabled():
            return {"ok": False, "error": "ruff not installed but ETHER_RUFF_GATE=1"}
        return {"ok": True, "skipped": True, "reason": "ruff not installed"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "ruff timeout"}
    out = (p.stdout or "") + (p.stderr or "")
    return {
        "ok": p.returncode == 0,
        "returncode": p.returncode,
        "stdout": out[-2000:],
        "score": 1.0 if p.returncode == 0 else 0.0,
    }
