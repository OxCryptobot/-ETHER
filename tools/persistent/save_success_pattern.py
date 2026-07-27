#!/usr/bin/env python3
"""Append a successful code pattern for later recall."""
from __future__ import annotations

import json
import pathlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import emit, read_input, repo_root


def main() -> None:
    inp = read_input()
    objective = inp.get("objective") or ""
    code = inp.get("code") or ""
    if not code:
        emit(False, error="code required")
    path = pathlib.Path(
        os.environ.get("ETHER_SUCCESS_PATTERNS_PATH")
        # Overridable so the test suite does not write mock runs into the
        # store that few_shot_pack replays into real prompts: 84 of 101
        # rows were "write hello" test artifacts served to the model as
        # worked examples.
        or repo_root() / "memory" / "learning" / "success_patterns.jsonl"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "objective": objective[:300],
        "code": code[:8000],
        "tags": inp.get("tags") or [],
        "confidence": inp.get("confidence"),
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    emit(True, saved=True, path=str(path))


if __name__ == "__main__":
    main()
