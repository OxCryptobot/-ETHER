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
    quar = (
        sorted(p.name for p in QUARANTINE.glob("*.py"))
        if QUARANTINE.exists() and include_quarantine
        else []
    )
    return {"persistent": pers, "quarantine": quar}


def resolve_tool(name: str) -> Optional[Path]:
    """Resolve a tool name to an executable path.

    Only PERSISTENT is searched. Names restricted to `[A-Za-z0-9_-]+`.
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
        if not isinstance(parsed, dict):
            parsed = {"value": parsed}

        ok = p.returncode == 0 and bool(parsed.get("ok", p.returncode == 0))
        # Flatten tool payload keys to the top level so callers that expect
        # `rm["files"]` (pipeline._fetch_repo_map) work the same as those that
        # correctly read `rm["result"]["files"]`. Nested `result` stays for
        # callers that already unwrap it.
        response: Dict[str, Any] = {
            "ok": ok,
            "returncode": p.returncode,
            "result": parsed,
            "stderr": (p.stderr or "")[-500:],
            "tool": path.name,
            "source": "persistent",
        }
        for k, v in parsed.items():
            if k not in response:
                response[k] = v
        return response
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timeout after {timeout}s", "tool": path.name}
    except Exception as e:
        return {"ok": False, "error": str(e), "tool": path.name}
