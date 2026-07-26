"""Shared helpers for @ETHER persistent tools.

Design rules:
- One job per tool
- JSON in / JSON out
- No network by default
- Fail closed on bad input
- PowerShell-friendly argv parsing
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict


def _coerce_json(raw: str) -> Dict[str, Any]:
    raw = (raw or "").strip()
    if not raw:
        return {}

    # 1) standard JSON
    try:
        val = json.loads(raw)
        return val if isinstance(val, dict) else {"value": val}
    except json.JSONDecodeError:
        pass

    # 2) PowerShell often leaves escaped quotes: {\"text\": \"hello\"}
    #    or mixes single/double quotes
    cleaned = raw
    # strip outer quotes if present
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (
        cleaned.startswith("'") and cleaned.endswith("'")
    ):
        cleaned = cleaned[1:-1]
    # unescape common PS escapes
    cleaned = cleaned.replace('\\"', '"').replace("\\'", "'")
    cleaned = cleaned.replace('\"', '"')
    try:
        val = json.loads(cleaned)
        return val if isinstance(val, dict) else {"value": val}
    except json.JSONDecodeError:
        pass

    # 3) single-quote → double-quote heuristic for simple objects
    alt = raw
    if alt.startswith("{") and "'" in alt and '"' not in alt:
        alt = alt.replace("'", '"')
        try:
            val = json.loads(alt)
            return val if isinstance(val, dict) else {"value": val}
        except json.JSONDecodeError:
            pass

    # 4) key=value pairs: text=hello path=foo.py
    if "=" in raw and not raw.startswith("{"):
        out: Dict[str, Any] = {}
        for part in re.split(r"\s+", raw):
            if "=" in part:
                k, v = part.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
        if out:
            return out

    # 5) bare path convenience
    if Path(raw).suffix or "/" in raw or "\\" in raw:
        return {"path": raw}

    raise json.JSONDecodeError("Could not parse tool input as JSON", raw, 0)


def read_input() -> Dict[str, Any]:
    if len(sys.argv) > 1:
        raw = " ".join(sys.argv[1:])
        return _coerce_json(raw)
    data = sys.stdin.read()
    if not data.strip():
        return {}
    return _coerce_json(data)


def emit(ok: bool, **payload: Any) -> None:
    out = {"ok": ok, **payload}
    sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    raise SystemExit(0 if ok else 1)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def safe_path(path: str | Path, root: Path | None = None) -> Path:
    root = (root or repo_root()).resolve()
    p = Path(path)
    if not p.is_absolute():
        p = (root / p).resolve()
    else:
        p = p.resolve()
    if root not in p.parents and p != root:
        raise ValueError(f"path escapes repo root: {p}")
    return p
