"""Cost / latency ledger — local runs + burst tokens (no dollar claims without rates)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "memory" / "runs"
BURST_LEDGER = ROOT / "memory" / "burst" / "ledger.jsonl"
OUT = ROOT / "memory" / "ledger" / "latest.json"


def _tail_runs(limit: int = 40) -> List[Dict[str, Any]]:
    if not RUNS.exists():
        return []
    files = sorted(
        [p for p in RUNS.glob("*.json") if p.name != "in_progress.json"],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]
    rows = []
    for f in files:
        try:
            rows.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    return rows


def _ms(stages: List[Dict[str, Any]]) -> float:
    return sum(float(s.get("duration_ms") or 0) for s in stages or [])


def compute_ledger() -> Dict[str, Any]:
    runs = _tail_runs(50)
    durations = [_ms(r.get("stages") or []) for r in runs]
    durations = [d for d in durations if d > 0]
    durations_sorted = sorted(durations)
    p50 = durations_sorted[len(durations_sorted) // 2] if durations_sorted else None
    avg = sum(durations) / len(durations) if durations else None

    stage_sums: Dict[str, List[float]] = {}
    burst_flagged = 0
    local_runs = 0
    for r in runs:
        if r.get("used_burst"):
            burst_flagged += 1
        else:
            local_runs += 1
        for s in r.get("stages") or []:
            name = str(s.get("stage") or "?")
            stage_sums.setdefault(name, []).append(float(s.get("duration_ms") or 0))

    stage_avg = {k: round(sum(v) / len(v), 1) for k, v in stage_sums.items() if v}

    burst_calls = 0
    burst_tokens = 0
    if BURST_LEDGER.exists():
        try:
            for line in BURST_LEDGER.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                burst_calls += 1
                try:
                    row = json.loads(line)
                    burst_tokens += int(row.get("tokens") or 0)
                except Exception:
                    pass
        except Exception:
            pass

    out = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "runs_sampled": len(runs),
        "avg_run_ms": round(avg, 1) if avg is not None else None,
        "p50_run_ms": round(p50, 1) if p50 is not None else None,
        "local_runs": local_runs,
        "burst_flagged_runs": burst_flagged,
        "burst_ledger_calls": burst_calls,
        "burst_tokens_sum": burst_tokens,
        "stage_avg_ms": stage_avg,
        "cost_note": "Tokens logged for burst only; $ requires your provider rate card.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out
