"""When to call titan burst — specialist, never default."""

from __future__ import annotations

import os
from typing import Optional


def burst_enabled() -> bool:
    return os.getenv("ETHER_BURST", "0") == "1"


def should_force_burst(
    *,
    attempt: int,
    strategy: str = "default",
    multifile: bool = False,
    tier: int = 0,
    hard_tag: bool = False,
    objective: str = "",
) -> bool:
    """Burst only on retry after fail, multifile, tier>=N, strategy, or HARD tag."""
    if not burst_enabled():
        return False
    if os.getenv("ETHER_FORCE_BURST", "0") == "1":
        return True
    if hard_tag or "[HARD]" in (objective or "").upper():
        return True
    on_fail = os.getenv("ETHER_BURST_ON_FAIL", "1") == "1"
    min_tier = int(os.getenv("ETHER_BURST_MIN_TIER", "2"))
    if attempt > 1 and on_fail:
        return True
    if strategy == "burst_on_fail" and attempt > 1:
        return True
    if multifile and attempt > 1:
        return True
    if tier >= min_tier and attempt > 1:
        return True
    # first attempt burst only if explicit hard
    if attempt == 1 and hard_tag:
        return True
    return False


def prefer_local_for_request(force_burst: bool, prefer_local: bool) -> bool:
    if force_burst:
        return False
    return prefer_local
