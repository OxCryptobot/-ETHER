"""Bench guardian — freeze risky autonomy if regression detected."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
BENCH_LATEST = ROOT / "memory" / "bench" / "latest.json"
GUARD_PATH = ROOT / "memory" / "bench" / "guardian.json"
BASELINE_PATH = ROOT / "memory" / "bench" / "baseline.json"


def guardian_enabled() -> bool:
    return os.getenv("ETHER_BENCH_GUARDIAN", "1") == "1"


def load_latest() -> Optional[Dict[str, Any]]:
    if not BENCH_LATEST.exists():
        return None
    try:
        return json.loads(BENCH_LATEST.read_text(encoding="utf-8"))
    except Exception:
        return None


def ensure_baseline(latest: Dict[str, Any]) -> Dict[str, Any]:
    if BASELINE_PATH.exists():
        try:
            return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    base = {
        "pass_rate": float(latest.get("pass_rate") or 0.0),
        "n": latest.get("n"),
        "set_at": datetime.now(timezone.utc).isoformat(),
    }
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(base, indent=2), encoding="utf-8")
    return base


def evaluate() -> Dict[str, Any]:
    """Return guardian decision. ok=False means freeze promote/fabricate."""
    if not guardian_enabled():
        return {"ok": True, "frozen": False, "reason": "guardian_disabled"}

    latest = load_latest()
    if not latest:
        # no bench yet — allow ops but flag
        decision = {
            "ok": True,
            "frozen": False,
            "reason": "no_bench_yet",
            "pass_rate": None,
            "baseline": None,
        }
        _save(decision)
        return decision

    base = ensure_baseline(latest)
    rate = float(latest.get("pass_rate") or 0.0)
    baseline = float(base.get("pass_rate") or 0.0)
    drop_tol = float(os.getenv("ETHER_BENCH_DROP_TOL", "0.10"))
    min_rate = float(os.getenv("ETHER_BENCH_MIN_PASS", "0.40"))

    frozen = False
    reason = "healthy"
    if rate < min_rate:
        frozen = True
        reason = f"pass_rate {rate:.3f} < min {min_rate}"
    elif baseline > 0 and (baseline - rate) > drop_tol:
        frozen = True
        reason = f"regression {baseline:.3f} -> {rate:.3f} exceeds tol {drop_tol}"

    decision = {
        "ok": not frozen,
        "frozen": frozen,
        "reason": reason,
        "pass_rate": rate,
        "baseline": baseline,
        "n": latest.get("n"),
        "bench_timestamp": latest.get("timestamp"),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    _save(decision)
    return decision


def _save(decision: Dict[str, Any]) -> None:
    GUARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    GUARD_PATH.write_text(json.dumps(decision, indent=2), encoding="utf-8")


def is_frozen() -> bool:
    d = evaluate()
    return bool(d.get("frozen"))
