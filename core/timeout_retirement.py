"""Timeout retirement plan — measurement + policy, no LIVE enqueue.

Combines timeout_diagnosis + live_fixture_policy into one operator artifact.
Target: live_timeout_rate < 0.25 before any wheels-off talk.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "timeout_retirement.json"
TARGET = float(os.getenv("ETHER_TIMEOUT_TARGET_RATE", "0.25"))


def _matches_deny(name: str, denied: Set[str]) -> bool:
    hay = (name or "").lower()
    return any(d and d in hay for d in denied)


def _projected_rate(diag: Dict[str, Any], denied: List[str]) -> Dict[str, Any]:
    """Estimate timeout rate if denied fixtures were never counted as LIVE."""
    denied_set = {d.lower() for d in denied if d}
    samples = list(diag.get("samples") or [])
    top = list(diag.get("top_fixtures") or [])

    # Prefer top_fixtures counts for timeouts; samples are partial
    timeout_kept = 0
    timeout_removed = 0
    for item in top:
        fx = str(item.get("fixture") or "")
        n = int(item.get("n") or 0)
        if _matches_deny(fx, denied_set):
            timeout_removed += n
        else:
            timeout_kept += n

    live_n = int(diag.get("live_n") or 0)
    timeout_n = int(diag.get("timeout_n") or 0)
    # Approximate: remove timeout hits that match deny; assume those rows were live
    live_adj = max(0, live_n - timeout_removed)
    timeout_adj = max(0, timeout_n - timeout_removed)
    # If top list under-counts, clamp
    if timeout_adj > live_adj and live_adj > 0:
        timeout_adj = live_adj

    rate = round(timeout_adj / live_adj, 4) if live_adj else None
    return {
        "live_n_adj": live_adj,
        "timeout_n_adj": timeout_adj,
        "timeout_removed": timeout_removed,
        "projected_timeout_rate": rate,
        "under_target": rate is not None and rate < TARGET,
        "sample_n": len(samples),
    }


def compute() -> Dict[str, Any]:
    try:
        from core.timeout_diagnosis import compute as diag_compute

        diag = diag_compute()
    except Exception as e:
        diag = {"error": str(e)[:160], "timeout_rate": None, "top_fixtures": []}

    try:
        from core.live_fixture_policy import publish as policy_publish

        policy = policy_publish()
    except Exception as e:
        policy = {"error": str(e)[:160], "denied": []}

    rate = diag.get("timeout_rate")
    top: List[Dict[str, Any]] = list(diag.get("top_fixtures") or [])
    denied = list(policy.get("denied") or [])
    projected = _projected_rate(diag, denied)

    actions: List[str] = []
    if rate is None:
        actions.append("run_timeout_diagnosis_when_scoreboards_present")
    elif rate >= TARGET:
        actions.append("keep_wheels_on")
        actions.append("do_not_enqueue_live")
        if top:
            actions.append(f"retire_top_fixture:{top[0].get('fixture')}")
        actions.append("prefer_scripted_steady_only")
        if projected.get("under_target"):
            actions.append("denylist_covers_historical_timeouts")
        else:
            actions.append("expand_denylist_or_scripted_only")
    else:
        actions.append("timeout_rate_under_target")
        actions.append("still_require_honest_rate_and_explicit_flags_for_soft_launch")

    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "timeout_rate": rate,
        "target_rate": TARGET,
        "ok": rate is not None and rate < TARGET,
        "live_n": diag.get("live_n"),
        "timeout_n": diag.get("timeout_n"),
        "top_fixtures": top[:8],
        "denied": denied,
        "projected": projected,
        "actions": actions,
        "note": (
            "Retirement plan only. Does not lift wheels or soft launch. "
            f"Target live_timeout_rate < {TARGET}. "
            "projected_* assumes denied fixtures never ran LIVE."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
