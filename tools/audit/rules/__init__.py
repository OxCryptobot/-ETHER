"""Rule implementations. Each module exposes RULES: {rule_id: check(ctx, meta)}."""

from __future__ import annotations

from . import (arch_boundaries, error_handling, measurement_integrity,
               perf_contracts, security_assumptions, state_integrity)

REGISTRY: dict = {}
for _mod in (arch_boundaries, error_handling, security_assumptions,
             state_integrity, perf_contracts, measurement_integrity):
    REGISTRY.update(_mod.RULES)
