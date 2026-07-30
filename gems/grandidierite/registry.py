"""Discover and run persistent / quarantine tools."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
PERSISTENT = ROOT / "tools" / "persistent"
QUARANTINE = ROOT / "tools" / "quarantine"


def list_tools(include_quarantine: bool = True) -> Dict[str, List[str]]:
    pers = sorted(p.name for p in PERSISTENT.glob("*.py")) if PERSISTENT.exists() else []
    quar = sorted(p.name for p in QUARANTINE.glob("*.py")) if QUARANTINE.exists() and include_quarantine else []
    return {"persistent": pers, "quarantine": quar}


def resolve_tool(name: str) -> Optional[Path]:
    """Resolve a tool name to an executable path.

    Only PERSISTENT is searched. QUARANTINE previously resolved here too,
    which meant `run_tool` executed unreviewed, self-fabricated code with
    sys.executable, cwd=ROOT and the full inherited environment — so the
    quarantine directory enforced nothing, contradicting SECURITY.md's claim
    that generated tools stay quarantined until explicitly promoted.

    Names are restricted to `[A-Za-z0-9_-]+` and the resolved path must stay
    inside PERSISTENT — `..` and subdirectory names return None.
    """
    if not name.endswith(".py"):
        name = f"{name}.py"
    stem = name[:-3]
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", stem):
        return None
    path = PERSISTENT / name
    try:
        if path.resolve().parent != PERSISTENT.resolve():
            return None
    except Exception:
        return None
    return path if path.exists() else None


def run_tool(name: str, payload: Optional[Dict[str, Any]] = None, timeout: int = 60) -> Dict[str, Any]:
    path = resolve_tool(name)
    if not path:
        return {"ok": False, "error": f"tool not found: {name}"}
    data = json.dumps(payload or {})
    try:
        p = subprocess.run(
            [sys.executable, str(path), data],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = (p.stdout or "").strip()
        try:
            parsed = json.loads(out) if out else {}
        except json.JSONDecodeError:
            parsed = {"raw": out}
        return {
            "ok": p.returncode == 0 and parsed.get("ok", p.returncode == 0),
            "returncode": p.returncode,
            "result": parsed,
            "stderr": (p.stderr or "")[-500:],
            "tool": path.name,
            "source": "persistent" if path.parent.name == "persistent" else "quarantine",
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timeout after {timeout}s", "tool": path.name}
    except Exception as e:
        return {"ok": False, "error": str(e), "tool": path.name}
