#!/usr/bin/env python3
"""Report Amethyst bandit arm stats."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import emit, repo_root


def main() -> None:
    path = repo_root() / "memory" / "learning" / "bandit.json"
    if not path.exists():
        emit(True, arms={}, note="no bandit state yet")
    data = json.loads(path.read_text(encoding="utf-8"))
    arms = data.get("arms") or {}
    ranked = sorted(
        (
            {
                "strategy": k,
                "pulls": v.get("pulls", 0),
                "mean": (v.get("total_reward", 0) / v["pulls"] if v.get("pulls") else 0),
                "total_reward": v.get("total_reward", 0),
            }
            for k, v in arms.items()
        ),
        key=lambda x: x["mean"],
        reverse=True,
    )
    emit(True, epsilon=data.get("epsilon"), ranked=ranked, updated_at=data.get("updated_at"))


if __name__ == "__main__":
    main()
