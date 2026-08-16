"""Live timeout diagnosis — which fixtures/strategies burn the clock.

Does not enqueue LIVE. Does not lift wheels. Measurement for 1D only.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "timeout_diagnosis.json"
TIMEOUT_FLOOR_S = float(os.getenv("ETHER_TIMEOUT_FLOOR_S", "120"))


def _is_timeout(row: Dict[str, Any], c: Dict[str, Any]) -> bool:
    if c.get("timeout"):
        return True
    ftype = str(row.get("failure_type") or "").lower()
    if "timeout" in ftype or "budget_exhaust" in ftype:
        return True
    try:
        dur = float(row.get("duration_s") or row.get("elapsed_s") or 0)
        if dur >= TIMEOUT_FLOOR_S and not c.get("ok"):
            return True
    except Exception:
        pass
    return False


def compute() -> Dict[str, Any]:
    from core.honest_live import collect_scoreboard_rows, classify_row

    rows = collect_scoreboard_rows()
    live_n = 0
    timeout_n = 0
    by_fixture: Counter = Counter()
    by_strategy: Counter = Counter()
    by_arm: Counter = Counter()
    samples: List[Dict[str, Any]] = []

    for r in rows:
        c = classify_row(r)
        if not c.get("live"):
            continue
        live_n += 1
        if not _is_timeout(r, c):
            continue
        timeout_n += 1
        fx = str(r.get("fixture") or r.get("name") or r.get("id") or "unknown")[:80]
        st = str(r.get("strategy") or "default")[:40]
        arm = str(r.get("arm") or r.get("mode") or "?")[:20]
        by_fixture[fx] += 1
        by_strategy[st] += 1
        by_arm[arm] += 1
        if len(samples) < 15:
            samples.append(
                {
                    "fixture": fx,
                    "strategy": st,
                    "arm": arm,
                    "duration_s": r.get("duration_s") or r.get("elapsed_s"),
                    "failure_type": r.get("failure_type"),
                }
            )

    rate = round(timeout_n / live_n, 4) if live_n else None
    top_fixtures = [
        {"fixture": k, "n": n} for k, n in by_fixture.most_common(12)
    ]
    top_strategies = [
        {"strategy": k, "n": n} for k, n in by_strategy.most_common(8)
    ]

    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "live_n": live_n,
        "timeout_n": timeout_n,
        "timeout_rate": rate,
        "timeout_floor_s": TIMEOUT_FLOOR_S,
        "top_fixtures": top_fixtures,
        "top_strategies": top_strategies,
        "by_arm": dict(by_arm),
        "samples": samples,
        "target_rate": 0.25,
        "ok": rate is not None and rate < 0.25 if rate is not None else False,
        "note": (
            "Measurement only. Prefer retiring top timeout fixtures from LIVE "
            "enqueue until rate < 0.25. Wheels stay ON."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
