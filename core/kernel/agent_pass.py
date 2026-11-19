"""Generate-loop measurement only. Never product PASS."""
from __future__ import annotations
from typing import Any, Dict
from core.kernel.honest import reject_generate_pass

def finalize_coding_result(row: Dict[str, Any], *, path: str) -> Dict[str, Any]:
    out = dict(row)
    out["path"] = path
    if path in {"generate", "agent_loop", "repair_heavy", "best_of_n", "resample"}:
        out["generate_fallback"] = True
        out["strategy"] = path
    return reject_generate_pass(out)
