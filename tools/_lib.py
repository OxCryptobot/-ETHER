"""Shared helpers for @ETHER persistent tools.

Design rules:
- One job per tool
- JSON in / JSON out
- No network by default
- Fail closed on bad input
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict


def read_input() -> Dict[str, Any]:
    if len(sys.argv) > 1:
        raw = " ".join(sys.argv[1:])
        if raw.strip().startswith("{"):
            return json.loads(raw)
        # treat as path key convenience
        return {"path": raw}
    data = sys.stdin.read().strip()
    if not data:
        return {}
    return json.loads(data)


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
