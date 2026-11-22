"""Strangle facade: coding results leave through the honest gate only."""
from __future__ import annotations
from typing import Any, Dict
from core.kernel.agent_pass import finalize_coding_result
from core.kernel.score_write import write_result

def finalize(row: Dict[str, Any], *, path: str = "tool_runtime", dest: str | None = None) -> Dict[str, Any]:
    honest = finalize_coding_result(row, path=path)
    if dest:
        try:
            write_result(dest, honest)
        except Exception:
            pass
    return honest
