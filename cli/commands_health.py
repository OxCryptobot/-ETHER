"""CLI helper for automated health checks."""

from __future__ import annotations

from typing import Any, Dict


def run_checks(*, skip_sandbox: bool = False) -> Dict[str, Any]:
    from core.health_check import run_health_checks

    return run_health_checks(include_sandbox_smoke=not skip_sandbox)
