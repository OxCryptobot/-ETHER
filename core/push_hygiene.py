"""Push hygiene status — detect log size threats before GH001.

Measurement only. Does not push.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
LOG = ROOT / "artifacts" / "host_agent_log.txt"
OUT = ROOT / "artifacts" / "push_hygiene.json"
GITHUB_LIMIT = 100 * 1024 * 1024
WARN_BYTES = 20 * 1024 * 1024


def compute() -> Dict[str, Any]:
    size = LOG.stat().st_size if LOG.exists() else 0
    ignored = False
    try:
        gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
        ignored = "host_agent_log.txt" in gi
    except Exception:
        ignored = False

    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "log_bytes": size,
        "log_mb": round(size / (1024 * 1024), 2),
        "github_limit_mb": 100,
        "warn_mb": 20,
        "over_warn": size >= WARN_BYTES,
        "over_github": size >= GITHUB_LIMIT,
        "gitignore_has_log": ignored,
        "ok": ignored and size < GITHUB_LIMIT,
        "note": "host_agent_log must stay local; never git-add",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
