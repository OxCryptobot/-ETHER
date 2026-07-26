"""Transparent SCOREBOARD.md — bench, quiz, ablation, health."""

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
    hidden = _j(ROOT / "memory" / "quiz" / "hidden_latest.json") or {}
    bench = _j(ROOT / "memory" / "bench" / "latest.json") or {}
    ablation = _j(ROOT / "memory" / "bench" / "ablation_latest.json") or {}
    cur = _j(ROOT / "memory" / "curriculum" / "state.json") or {}
    guard = _j(ROOT / "memory" / "bench" / "guardian.json") or {}
    ledger = _j(ROOT / "memory" / "ledger" / "latest.json") or {}

    burst_calls = 0
    bl = ROOT / "memory" / "burst" / "ledger.jsonl"
    if bl.exists():
        try:
            burst_calls = sum(1 for line in bl.read_text(encoding="utf-8").splitlines() if line.strip())
        except Exception:
            pass

    model = os.getenv("ETHER_PRIMARY_MODEL", "")
    lines = [
        "# @ETHER Scoreboard",
        "",
        f"_Updated: {datetime.now(timezone.utc).isoformat()}_",
        "",
        "> Local verified coding agent · learn from gated runs · frontier burst only when local fails · public holdout scores.",
        "",
        "## Primary metrics",
        "",
        "| Metric | Value |",
        "|--------|------:|",
        f"| Bench pass_rate | {bench.get('pass_rate', health.get('pass_rate'))} |",
        f"| Quiz holdout pass_rate | {quiz.get('pass_rate', '—')} |",
        f"| Hidden-test pass_rate | {hidden.get('pass_rate', '—')} |",
        f"| Healthy | {health.get('healthy')} |",
        f"| Stale | {health.get('stale')} |",
        f"| Unhealthy reasons | {', '.join(health.get('unhealthy_reasons') or []) or '—'} |",
        f"| Guardian frozen | {guard.get('frozen', False)} |",
        f"| Curriculum tier | {cur.get('tier', 0)} |",
        f"| Verified wins / losses | {cur.get('wins', 0)}/{cur.get('losses', 0)} |",
        f"| Burst ledger calls | {burst_calls} |",
        f"| Avg run ms | {ledger.get('avg_run_ms', '—')} |",
        f"| Primary model | `{model}` |",
        "",
        "## Burst ablation (science)",
        "",
    ]
    if ablation:
        lines += [
            "| Mode | pass_rate | avg_ms |",
            "|------|----------:|-------:|",
            f"| OFF | {ablation.get('pass_rate_off')} | {ablation.get('avg_ms_off')} |",
            f"| ON | {ablation.get('pass_rate_on')} | {ablation.get('avg_ms_on')} |",
            f"| Δ | {ablation.get('delta_pass_rate')} | {ablation.get('delta_avg_ms')} |",
            "",
        ]
    else:
        lines += [
            "_No ablation yet. Run: `python scripts/burst_ablation.py --limit 10`_",
            "",
        ]

    lines += [
        "## Honesty rules",
        "",
        "1. Holdout + hidden IDs never enter curriculum sampling.",
        "2. Print-only success is not formal tests (confidence soft-capped).",
        "3. Tier promote requires verification_score ≥ 0.7 and total_tests > 0.",
        "4. Burst never skips sandbox or audit.",
        "5. Healthy requires fresh bench **and** quiz (<24h).",
        "",
        "## Refresh",
        "",
        "```powershell",
        "python scripts/measurement_day.py",
        "python scripts/burst_ablation.py --limit 10   # needs ETHER_BURST=1 + key",
        "python scripts/hidden_quiz.py --limit 10",
        "```",
        "",
    ]
    SCOREBOARD.write_text("\n".join(lines), encoding="utf-8")
    return {
        "path": str(SCOREBOARD),
        "quiz": quiz.get("pass_rate"),
        "bench": bench.get("pass_rate"),
        "hidden": hidden.get("pass_rate"),
        "ablation_delta": ablation.get("delta_pass_rate"),
        "healthy": health.get("healthy"),
    }
