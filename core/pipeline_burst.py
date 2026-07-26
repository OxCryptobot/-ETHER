"""Thin adapter so pipeline can call burst policy without mega-diff."""

from __future__ import annotations

from core.burst_policy import should_force_burst, prefer_local_for_request, burst_enabled


def _current_tier() -> int:
    try:
        from core.curriculum import current_tier_index

        return int(current_tier_index())
    except Exception:
        return 0


def decide_burst(attempt: int, strategy: str, objective: str, tier: int | None = None) -> bool:
    o = (objective or "").lower()
    multifile = any(k in o for k in ("class", "module", "refactor", "file", "package", "multi"))
    hard = "[hard]" in o
    t = _current_tier() if tier is None else int(tier)
    return should_force_burst(
        attempt=attempt,
        strategy=strategy,
        multifile=multifile,
        tier=t,
        hard_tag=hard,
        objective=objective,
    )


__all__ = ["decide_burst", "prefer_local_for_request", "burst_enabled"]
