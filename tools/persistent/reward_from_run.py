#!/usr/bin/env python3
"""Recompute reward from a saved pipeline run JSON."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import emit, read_input, repo_root, safe_path

# inline minimal reward to avoid import issues when run standalone

def compute_reward(exit_code, confidence, audit_approved, retries=0):
    r = 0.0
    r += 1.0 if exit_code == 0 else (-0.7 if exit_code is not None else -0.3)
    r += 0.5 * max(0.0, min(1.0, float(confidence or 0)))
    r += 0.3 if audit_approved else -0.2
    r -= 0.15 * max(0, int(retries or 0))
    return round(r, 4)


def main() -> None:
    inp = read_input()
    path = inp.get("path")
    if not path:
        emit(False, error="path to run json required")
    data = json.loads(safe_path(path, repo_root()).read_text(encoding="utf-8"))
    sand = data.get("sandbox") or {}
    audit = data.get("audit") or {}
    reward = compute_reward(
        sand.get("exit_code"),
        data.get("confidence") or 0,
        bool(audit.get("approved")),
        data.get("retries") or 0,
    )
    emit(True, reward=reward, task_id=data.get("task_id"), status=data.get("status"))


if __name__ == "__main__":
    main()
