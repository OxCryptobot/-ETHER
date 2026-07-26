#!/usr/bin/env python3
"""Burst ablation: same holdout tasks with burst OFF vs ON. Science, not marketing."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.dotenv import load_dotenv
from core.pipeline import Pipeline
from core.scoreboard import write_scoreboard

load_dotenv(ROOT / ".env")

HOLDOUT = ROOT / "memory" / "quizzes" / "holdout_v1.json"
OUT_DIR = ROOT / "memory" / "bench"


def _run_set(tasks: list, burst_on: bool) -> dict:
    prev = os.environ.get("ETHER_BURST")
    prev_fail = os.environ.get("ETHER_BURST_ON_FAIL")
    if burst_on:
        os.environ["ETHER_BURST"] = "1"
        os.environ["ETHER_BURST_ON_FAIL"] = "1"
    else:
        os.environ["ETHER_BURST"] = "0"
        os.environ["ETHER_BURST_ON_FAIL"] = "0"
    pipe = Pipeline()
    rows = []
    t0 = time.perf_counter()
    for i, t in enumerate(tasks, 1):
        print(f"  [{'ON' if burst_on else 'OFF'} {i}/{len(tasks)}] {t.get('id')} ...", flush=True)
        st = time.perf_counter()
        r = pipe.run(t["objective"])
        ms = round((time.perf_counter() - st) * 1000, 1)
        ok = r.status == "complete" and r.sandbox and r.sandbox.exit_code == 0
        rows.append(
            {
                "id": t.get("id"),
                "ok": ok,
                "ms": ms,
                "confidence": r.confidence,
                "verification_score": r.verification_score,
                "used_burst": bool(getattr(r, "used_burst", False)),
                "total_tests": r.sandbox.total_tests if r.sandbox else 0,
            }
        )
    if prev is None:
        os.environ.pop("ETHER_BURST", None)
    else:
        os.environ["ETHER_BURST"] = prev
    if prev_fail is None:
        os.environ.pop("ETHER_BURST_ON_FAIL", None)
    else:
        os.environ["ETHER_BURST_ON_FAIL"] = prev_fail

    n = len(rows)
    passed = sum(1 for x in rows if x["ok"])
    return {
        "burst": burst_on,
        "n": n,
        "pass": passed,
        "pass_rate": round(passed / max(1, n), 3),
        "avg_ms": round(sum(x["ms"] for x in rows) / max(1, n), 1),
        "burst_flags": sum(1 for x in rows if x["used_burst"]),
        "duration_s": round(time.perf_counter() - t0, 2),
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()

    if not HOLDOUT.exists():
        print("missing holdout_v1.json — run expand_holdout.py first", file=sys.stderr)
        return 2

    data = json.loads(HOLDOUT.read_text(encoding="utf-8"))
    tasks = list(data.get("tasks") or [])[: args.limit]
    print(f"Ablation n={len(tasks)} OFF then ON", flush=True)
    off = _run_set(tasks, burst_on=False)
    on = _run_set(tasks, burst_on=True)

    delta = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "n": len(tasks),
        "pass_rate_off": off["pass_rate"],
        "pass_rate_on": on["pass_rate"],
        "delta_pass_rate": round(on["pass_rate"] - off["pass_rate"], 3),
        "avg_ms_off": off["avg_ms"],
        "avg_ms_on": on["avg_ms"],
        "delta_avg_ms": round(on["avg_ms"] - off["avg_ms"], 1),
        "burst_flags_on": on["burst_flags"],
        "off": off,
        "on": on,
        "note": "Outcome change is science; model name alone is marketing.",
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = OUT_DIR / f"ablation_{day}.json"
    path.write_text(json.dumps(delta, indent=2), encoding="utf-8")
    (OUT_DIR / "ablation_latest.json").write_text(json.dumps(delta, indent=2), encoding="utf-8")

    md = [
        f"# Burst ablation {day}",
        "",
        f"| Mode | pass_rate | avg_ms | burst_flags |",
        f"|------|----------:|-------:|------------:|",
        f"| OFF | {off['pass_rate']} | {off['avg_ms']} | 0 |",
        f"| ON | {on['pass_rate']} | {on['avg_ms']} | {on['burst_flags']} |",
        f"| Δ | {delta['delta_pass_rate']} | {delta['delta_avg_ms']} | — |",
        "",
        "_Local plans+verifies always; burst only on policy triggers._",
    ]
    (OUT_DIR / f"ablation_{day}.md").write_text("\n".join(md), encoding="utf-8")
    try:
        write_scoreboard()
    except Exception:
        pass
    print(json.dumps({k: delta[k] for k in delta if k not in ("off", "on")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
