"""Local self-learn. No Grok. Infra FAILs never become lessons."""
from __future__ import annotations
from typing import Any, Dict
from core.kernel.critique import valid_critique
from core.kernel.memory_schema import stamp

INFRA = frozenset({"provider_timeout", "timeout", "ollama_down", "argv_denied", "path_jail"})

def lesson_from_fail(last: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not last or last.get("ok") is True:
        return None
    tail = str(last.get("tail") or last.get("error") or last.get("note") or "")
    err = str(last.get("error") or "")
    if err in INFRA or "Timeout" in tail:
        return None
    row = {
        "root_cause": "unknown",
        "evidence": (tail or err or "fail")[:400],
        "smallest_experiment": "re-run targeted kernel pytest after one surgical patch",
        "confidence": 0.45,
        "job_id": last.get("job_id"),
    }
    if "parse" in tail.lower():
        row["root_cause"] = "parse_fail"
    elif "no_progress" in tail.lower():
        row["root_cause"] = "no_progress"
    if not valid_critique(row):
        return None
    return stamp(row)
