"""Cost / latency ledger — local vs burst timing from runs + burst ledger."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "memory" / "runs"
BURST_LEDGER = ROOT / "memory" / "burst" / "ledger.jsonl"
OUT = ROOT / "memory" / "ledger" / "latest.json"


def _tail_jsonl(path: Path, n: int = 200) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[-n:]:
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        return []
    return rows


def compute_ledger() -> Dict[str, Any]:
    stage_ms: Dict[str, List[float]] = {}
    run_total_ms: List[float] = []
    burst_runs = 0
    local_runs = 0

    if RUNS.exists():
        files = sorted(RUNS.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:40]
        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get("used_burst"):
                burst_runs += 1
            else:
                local_runs += 1
            total = 0.0
            for s in data.get("stages") or []:
                ms = float(s.get("duration_ms") or 0)
                st = str(s.get("stage") or "?")
                stage_ms.setdefault(st, []).append(ms)
                total += ms
            if total:
                run_total_ms.append(total)

    burst_rows = _tail_jsonl(BURST_LEDGER, 100)
    burst_ok = sum(1 for r in burst_rows if r.get("ok"))
    burst_fail = sum(1 for r in burst_rows if not r.get("ok"))
    tokens = [int(r.get("tokens") or 0) for r in burst_rows if r.get("tokens")]

    def avg(xs: List[float]) -> float:
        return round(sum(xs) / len(xs), 1) if xs else 0.0

    stage_avg = {k: avg(v) for k, v in sorted(stage_ms.items(), key=lambda kv: -avg(kv[1]))}

    out = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "runs_sampled": local_runs + burst_runs,
        "local_runs": local_runs,
        "burst_flagged_runs": burst_runs,
        "avg_run_ms": avg(run_total_ms),
        "p50_run_ms": round(sorted(run_total_ms)[len(run_total_ms) // 2], 1) if run_total_ms else 0.0,
        "stage_avg_ms": stage_avg,
        "burst_ledger_calls": len(burst_rows),
        "burst_ok": burst_ok,
        "burst_fail": burst_fail,
        "burst_tokens_sum": sum(tokens),
        "burst_tokens_avg": round(sum(tokens) / len(tokens), 1) if tokens else 0,
        # no $ without price table — keep honest
        "cost_note": "Token counts logged; $ requires provider price table (not assumed).",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out
