"""Microbench cadence helper — when should the hot-path bench run.

Does not enqueue by itself. Foreman/host can call should_run().
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
BENCH = ROOT / "artifacts" / "microbench.json"
DEFAULT_INTERVAL_S = int(os.getenv("ETHER_MICROBENCH_INTERVAL_S", "300"))


def _age_s(iso: Optional[str]) -> Optional[float]:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds()
    except Exception:
        return None


def should_run(*, interval_s: Optional[int] = None) -> Dict[str, Any]:
    interval = interval_s if interval_s is not None else DEFAULT_INTERVAL_S
    if not BENCH.exists():
        return {"run": True, "reason": "no_prior", "interval_s": interval, "age_s": None}
    try:
        data = json.loads(BENCH.read_text(encoding="utf-8"))
    except Exception:
        return {"run": True, "reason": "unreadable", "interval_s": interval, "age_s": None}
    age = _age_s(data.get("updated") or data.get("timestamp"))
    if age is None:
        return {"run": True, "reason": "no_timestamp", "interval_s": interval, "age_s": None}
    if age >= interval:
        return {"run": True, "reason": "stale", "interval_s": interval, "age_s": round(age, 1)}
    return {
        "run": False,
        "reason": "fresh",
        "interval_s": interval,
        "age_s": round(age, 1),
        "ok_last": data.get("ok"),
    }


def maybe_run() -> Dict[str, Any]:
    """Run microbench only if schedule says so."""
    decision = should_run()
    if not decision.get("run"):
        return {"skipped": True, **decision}
    from core.microbench import run

    out = run()
    out["schedule"] = decision
    return out


if __name__ == "__main__":
    print(json.dumps(maybe_run(), indent=2))
