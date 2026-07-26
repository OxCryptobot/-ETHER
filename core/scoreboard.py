"""Transparent SCOREBOARD.md — primary public metrics."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
SCOREBOARD = ROOT / "SCOREBOARD.md"


def _j(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def write_scoreboard() -> Dict[str, Any]:
    from core.health_metric import compute_health

    health = compute_health()
    quiz = _j(ROOT / "memory" / "quiz" / "latest.json") or {}
    bench = _j(ROOT / "memory" / "bench" / "latest.json") or {}
    cur = _j(ROOT / "memory" / "curriculum" / "state.json") or {}
    guard = _j(ROOT / "memory" / "bench" / "guardian.json") or {}

    burst_calls = 0
    ledger = ROOT / "memory" / "burst" / "ledger.jsonl"
    if ledger.exists():
        try:
            burst_calls = sum(1 for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip())
        except Exception:
            pass

    model = os.getenv("ETHER_PRIMARY_MODEL", "")
    lines = [
        "# @ETHER Scoreboard",
        "",
        f"_Updated: {datetime.now(timezone.utc).isoformat()}_",
        "",
        "## Primary metrics (ungameable intent)",
        "",
        "| Metric | Value |",
        "|--------|------:|",
        f"| Bench pass_rate | {bench.get('pass_rate', health.get('pass_rate'))} |",
        f"| Quiz holdout pass_rate | {quiz.get('pass_rate', '—')} |",
        f"| Healthy | {health.get('healthy')} |",
        f"| Guardian frozen | {guard.get('frozen', False)} |",
        f"| Curriculum tier | {cur.get('tier', 0)} |",
        f"| Curriculum wins/losses | {cur.get('wins', 0)}/{cur.get('losses', 0)} |",
        f"| Burst calls (ledger) | {burst_calls} |",
        f"| Primary model | `{model}` |",
        "",
        "## Notes",
        "",
        "- Holdout quiz IDs are excluded from flywheel curriculum sampling.",
        "- Print-only sandbox success is **not** counted as formal tests (verification soft-cap).",
        "- Cloud burst only when `ETHER_BURST=1` and budget remains; sandbox still required.",
        "",
        "## How to refresh",
        "",
        "```powershell",
        "python scripts/bench.py --fast",
        "python scripts/quiz.py --limit 5",
        "python -c \"from core.scoreboard import write_scoreboard; write_scoreboard()\"",
        "```",
        "",
    ]
    SCOREBOARD.write_text("\n".join(lines), encoding="utf-8")
    return {"path": str(SCOREBOARD), "quiz": quiz.get("pass_rate"), "bench": bench.get("pass_rate")}
