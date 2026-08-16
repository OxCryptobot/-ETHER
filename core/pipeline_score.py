"""Pipeline score + degrade pure helpers (strangler slice).

No Pipeline import. Safe unit tests. Future wire behind flag only.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


def clamp_score(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        x = float(default)
    if x != x:  # NaN
        x = float(default)
    return max(0.0, min(1.0, x))


def merge_degraded(
    existing: Optional[Iterable[str]] = None, *markers: str
) -> List[str]:
    out: List[str] = []
    for m in list(existing or []) + list(markers):
        s = str(m or "").strip()
        if s and s not in out:
            out.append(s)
    return out


def terminal_fail_envelope(
    *,
    stage: str,
    marker: str,
    score: float = 0.0,
    msg: str = "",
    degraded: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Standard FAIL envelope shape used across pipeline terminals."""
    deg = merge_degraded(degraded, marker)
    return {
        "ok": False,
        "score": clamp_score(score),
        "stage": stage,
        "fail_msg": msg or marker,
        "degraded": deg,
        "marker": marker,
    }


def terminal_ok_envelope(
    *,
    score: float = 1.0,
    degraded: Optional[Iterable[str]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "ok": True,
        "score": clamp_score(score, default=1.0),
        "degraded": merge_degraded(degraded),
    }
    if extra:
        out.update(extra)
    return out
