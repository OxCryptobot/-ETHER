"""Honest tool-path KPI — primary 1A metric for Control Matrix.

Critical fix #5: tool_runtime 0/447 must be visible as honest_pass/attempts.
Writes artifacts/honest_kpi.json for dashboard.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "honest_kpi.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute(rows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    if rows is None:
        try:
            from core.honest_live import collect_scoreboard_rows, classify_row

            raw = collect_scoreboard_rows()
            classified = [classify_row(r) for r in raw]
        except Exception as e:
            return {
                "updated": _now(),
                "ok": False,
                "error": str(e)[:200],
                "honest_tool_pass": 0,
                "tool_attempts": 0,
                "honest_rate": None,
                "disguised_pass_n": 0,
            }
    else:
        from core.honest_live import classify_row

        classified = [classify_row(r) for r in rows]

    toolish = [c for c in classified if c.get("toolish") or c.get("honest")]
    # Prefer rows that look like tool path attempts
    attempts = [c for c in classified if c.get("toolish") or c.get("live") or c.get("ok")]
    honest = sum(1 for c in classified if c.get("honest"))
    disguised = sum(1 for c in classified if c.get("disguised_pass"))
    tool_attempts = max(len(toolish), 1) if toolish else len(attempts)
    honest_rate = round(honest / tool_attempts, 4) if tool_attempts else None

    payload: Dict[str, Any] = {
        "updated": _now(),
        "ok": True,
        "honest_tool_pass": honest,
        "tool_attempts": tool_attempts,
        "honest_rate": honest_rate,
        "disguised_pass_n": disguised,
        "n_rows": len(classified),
        "primary_kpi": f"{honest}/{tool_attempts}",
        "gate": "is_honest_tool_path_pass",
        "note": "Primary 1A KPI. Generate-fallback never counts as honest pass.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
