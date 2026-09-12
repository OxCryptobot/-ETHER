"""Keep/revert traces so local self-build can evolve."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def _root() -> Path:
    import os
    env = os.environ.get("ETHER_ROOT")
    if env and (Path(env) / "scripts").is_dir():
        return Path(env).resolve()
    win = Path(r"C:\\Users\\Otcde\\ETHER")
    if (win / "scripts").is_dir():
        return win.resolve()
    return Path(__file__).resolve().parents[1]


TRACE = "artifacts/self_build_trace.jsonl"


def record(row: Dict[str, Any]) -> Path:
    p = _root() / TRACE
    p.parent.mkdir(parents=True, exist_ok=True)
    row = dict(row)
    row["ts"] = datetime.now(timezone.utc).isoformat()
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row)[:3000] + "\n")
    return p


def generation() -> int:
    p = _root() / TRACE
    if not p.is_file():
        return 0
    return sum(1 for _ in p.open(encoding="utf-8"))
