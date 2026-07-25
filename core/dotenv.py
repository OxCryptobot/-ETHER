"""Minimal .env loader for @ETHER (no extra dependency)."""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: Path | None = None, override: bool = False) -> Path | None:
    """Load KEY=VALUE pairs from .env into os.environ.

    Does not override existing env vars unless override=True.
    Returns path loaded, or None if missing.
    """
    env_path = path or Path.cwd() / ".env"
    if not env_path.exists():
        # try repo root relative to this file
        alt = Path(__file__).resolve().parents[1] / ".env"
        if alt.exists():
            env_path = alt
        else:
            return None

    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if not key:
            continue
        if override or key not in os.environ or os.environ.get(key, "") == "":
            os.environ[key] = val
    return env_path
