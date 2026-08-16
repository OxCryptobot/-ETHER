"""Pure bandit / strategy context helper (strangler slice)."""
from __future__ import annotations

from typing import Any, Dict


def bandit_context(objective: str, tier: int = 0, fail_kind: str = "") -> Dict[str, Any]:
    try:
        from core.multifile import is_multifile_objective

        multifile = is_multifile_objective(objective)
    except Exception:
        o = (objective or "").lower()
        multifile = any(
            k in o for k in ("class", "module", "refactor", "file", "package", "multi")
        )
    return {"tier": tier, "fail_kind": fail_kind, "multifile": multifile}
