#!/usr/bin/env python3
"""Always materialize memory/bench/health.json (even before first full bench)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.health_metric import compute_health
from core.bench_guardian import evaluate


def main() -> int:
    # seed latest if missing so health has something
    latest = ROOT / "memory" / "bench" / "latest.json"
    if not latest.exists():
        latest.parent.mkdir(parents=True, exist_ok=True)
        seed = {
            "timestamp": "1970-01-01T00:00:00+00:00",
            "n": 0,
            "pass": 0,
            "pass_rate": 0.0,
            "duration_s": 0.0,
            "results": [],
            "note": "seed — run scripts/bench.py for real score",
        }
        latest.write_text(json.dumps(seed, indent=2), encoding="utf-8")
    h = compute_health()
    g = evaluate()
    print(json.dumps({"health": h, "guardian": g}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
