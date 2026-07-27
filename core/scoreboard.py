"""Transparent SCOREBOARD — dense dated metrics."""

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
    from core.dotenv import load_dotenv
    from core.health_metric import compute_health

    # The scoreboard records which model produced these numbers. Callers that
    # invoke this directly (weekly_scoreboard.py runs it via `python -c`) never
    # load .env, so ETHER_PRIMARY_MODEL came back empty and every scoreboard
    # was written with an unattributed model.
    load_dotenv(ROOT / ".env")

    health = compute_health()
    quiz = _j(ROOT / "memory" / "quiz" / "latest.json") or {}
    hidden = _j(ROOT / "memory" / "quiz" / "hidden_latest.json") or {}
    dataset = _j(ROOT / "memory" / "quiz" / "dataset_latest.json") or {}
    bench = _j(ROOT / "memory" / "bench" / "latest.json") or {}
    ablation = _j(ROOT / "memory" / "bench" / "ablation_latest.json") or {}
    cur = _j(ROOT / "memory" / "curriculum" / "state.json") or {}
    guard = _j(ROOT / "memory" / "bench" / "guardian.json") or {}
    ledger = _j(ROOT / "memory" / "ledger" / "latest.json") or {}
    fg = _j(ROOT / "memory" / "experience" / "failure_graph.json") or {}
    nodes = (fg.get("nodes") or {}) if isinstance(fg, dict) else {}

    burst_calls = 0
    bl = ROOT / "memory" / "burst" / "ledger.jsonl"
    if bl.exists():
        try:
            burst_calls = sum(1 for line in bl.read_text(encoding="utf-8").splitlines() if line.strip())
        except Exception:
            pass

    pass_n = fail_n = 0
    for name, counter in (("pass.jsonl", "pass"), ("fail.jsonl", "fail")):
        p = ROOT / "memory" / "experience" / name
        if p.exists():
            try:
                n = sum(1 for line in p.read_text(encoding="utf-8").splitlines() if line.strip())
                if counter == "pass":
                    pass_n = n
                else:
                    fail_n = n
            except Exception:
                pass

    model = os.getenv("ETHER_PRIMARY_MODEL", "")
    lines = [
        "# @ETHER Scoreboard",
        "",
        f"_Updated: {datetime.now(timezone.utc).isoformat()}_",
        "",
        "> Local verified agent · learns from gated runs · frontier burst only on policy · public holdout scores.",
        "",
        "## Primary metrics",
        "",
        "| Metric | Value |",
        "|--------|------:|",
        f"| Bench pass_rate | {bench.get('pass_rate', health.get('pass_rate'))} |",
        f"| Bench mode / n | {bench.get('mode', '—')} / {bench.get('n', '—')} |",
        f"| Quiz holdout pass_rate | {quiz.get('pass_rate', '—')} |",
        f"| Hidden HE pass_rate | {hidden.get('pass_rate', '—')} |",
        f"| Dataset (MBPP-lite) pass_rate | {dataset.get('pass_rate', '—')} |",
        f"| Healthy | {health.get('healthy')} |",
        f"| Stale reasons | {', '.join(health.get('unhealthy_reasons') or []) or '—'} |",
        f"| Guardian frozen | {guard.get('frozen', False)} |",
        f"| Curriculum tier | {cur.get('tier', 0)} |",
        f"| Verified wins/losses | {cur.get('wins', 0)}/{cur.get('losses', 0)} |",
        f"| Experience PASS/FAIL | {pass_n}/{fail_n} |",
        f"| Failure graph nodes | {len(nodes)} |",
        f"| Burst ledger calls | {burst_calls} |",
        f"| Avg run ms | {ledger.get('avg_run_ms', '—')} |",
        f"| Primary model | `{model}` |",
        "",
        "## Burst ablation",
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
        lines += ["_Run `python scripts/burst_ablation.py --limit 10` with burst env._", ""]

    lines += [
        "## Feedback loops active",
        "",
        "- Experience vault → few-shot + fail-kind repair bias",
        "- Offline BM25 RAG on repo (no Qdrant required)",
        "- Failure graph → repair templates",
        "- Contextual bandit + process rewards",
        "- Holdout/hidden IDs excluded from curriculum",
        "- Multifile markers `# file: name.py` under memory/scratch only",
        "",
        "## Refresh",
        "",
        "```powershell",
        "python scripts/weekly_scoreboard.py",
        "python scripts/burst_ablation.py --limit 10",
        "```",
        "",
        "See COUSIN.md for two-person ops without chat babysitting.",
        "",
    ]
    SCOREBOARD.write_text("\n".join(lines), encoding="utf-8")
    return {
        "path": str(SCOREBOARD),
        "healthy": health.get("healthy"),
        "bench": bench.get("pass_rate"),
        "quiz": quiz.get("pass_rate"),
        "dataset": dataset.get("pass_rate"),
        "ablation_delta": ablation.get("delta_pass_rate"),
    }
