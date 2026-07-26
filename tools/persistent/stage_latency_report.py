#!/usr/bin/env python3
"""Average pipeline stage latency from memory/runs."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import emit, repo_root


def main() -> None:
    runs = repo_root() / "memory" / "runs"
    if not runs.exists():
        emit(True, stages={}, note="no runs")
    totals: dict[str, list[float]] = defaultdict(list)
    count = 0
    for f in sorted(runs.glob("*.json"))[-100:]:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        count += 1
        for s in data.get("stages") or []:
            totals[s.get("stage", "?")].append(float(s.get("duration_ms") or 0))
    summary = {
        k: {"avg_ms": round(sum(v) / len(v), 1), "n": len(v), "max_ms": round(max(v), 1)}
        for k, v in totals.items()
        if v
    }
    emit(True, runs_sampled=count, stages=summary)


if __name__ == "__main__":
    main()
