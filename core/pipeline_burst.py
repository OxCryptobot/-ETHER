"""Thin adapter so pipeline can call burst policy without mega-diff."""

from __future__ import annotations

from core.burst_policy import should_force_burst, prefer_local_for_request, burst_enabled


def decide_burst(attempt: int, strategy: str, objective: str, tier: int = 0) -> bool:
    o = (objective or "").lower()
    multifile = any(k in o for k in ("class", "module", "refactor", "file", "package", "multi"))
    hard = "[hard]" in o
    return should_force_burst(
        attempt=attempt,
        strategy=strategy,
        multifile=multifile,
        tier=tier,
        hard_tag=hard,
        objective=objective,
    )


__all__ = ["decide_burst", "prefer_local_for_request", "burst_enabled"]
