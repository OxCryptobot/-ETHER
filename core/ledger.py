"""Cost / latency ledger — local runs + burst usage (no fake $ without rates)."""

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


def _burst_stats() -> Dict[str, Any]:
    if not BURST_LEDGER.exists():
        return {"calls": 0, "ok": 0, "tokens": 0}
    calls = ok = tokens = 0
    try:
        for line in BURST_LEDGER.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            calls += 1
            if r.get("ok"):
                ok += 1
            tokens += int(r.get("tokens") or 0)
    except Exception:
        pass
    return {"calls": calls, "ok": ok, "tokens": tokens}


def compute_ledger() -> Dict[str, Any]:
    runs = _tail_runs(50)
    durations: List[float] = []
    stage_ms: Dict[str, List[float]] = {}
    burst_flagged = 0
    local_runs = 0

    for r in runs:
        local_runs += 1
        if r.get("used_burst"):
            burst_flagged += 1
        started = r.get("started_at")
        finished = r.get("finished_at")
        # sum stage ms as proxy
        total = 0.0
        for s in r.get("stages") or []:
            ms = float(s.get("duration_ms") or 0)
            total += ms
            st = str(s.get("stage") or "?")
            stage_ms.setdefault(st, []).append(ms)
        if total > 0:
            durations.append(total)

    def avg(xs: List[float]) -> float:
        return round(sum(xs) / len(xs), 1) if xs else 0.0

    durations_sorted = sorted(durations)
    p50 = durations_sorted[len(durations_sorted) // 2] if durations_sorted else 0.0
    burst = _burst_stats()

    out = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "sample_runs": len(runs),
        "local_runs": local_runs,
        "burst_flagged_runs": burst_flagged,
        "avg_run_ms": avg(durations),
        "p50_run_ms": round(p50, 1),
        "stage_avg_ms": {k: avg(v) for k, v in stage_ms.items()},
        "burst_ledger_calls": burst["calls"],
        "burst_ledger_ok": burst["ok"],
        "burst_tokens_sum": burst["tokens"],
        "cost_note": (
            "Token/$ not estimated without provider rate cards. "
            "Track burst_tokens_sum and call counts; set rates externally if needed."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out
