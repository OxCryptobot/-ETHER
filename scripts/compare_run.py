#!/usr/bin/env python3
"""Side-by-side log runner — records @ETHER results for holdout tasks (manual peers)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.dotenv import load_dotenv
from core.pipeline import Pipeline

load_dotenv(ROOT / ".env")

HOLDOUT = ROOT / "memory" / "quizzes" / "holdout_v1.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()

    data = json.loads(HOLDOUT.read_text(encoding="utf-8"))
    tasks = list(data.get("tasks") or [])[: args.limit]
    pipe = Pipeline()
    rows = []
    t0 = time.perf_counter()
    for i, t in enumerate(tasks, 1):
        print(f"[compare {i}/{len(tasks)}] {t.get('id')} ...", flush=True)
        st = time.perf_counter()
        r = pipe.run(t["objective"])
        ms = round((time.perf_counter() - st) * 1000, 1)
        ok = r.status == "complete" and r.sandbox and r.sandbox.exit_code == 0
        rows.append(
            {
                "id": t.get("id"),
                "ether_ok": ok,
                "ether_ms": ms,
                "confidence": r.confidence,
                "verification_score": r.verification_score,
                "strategy": r.strategy,
                "used_burst": r.used_burst,
                "aider_ok": None,
                "continue_ok": None,
                "cursor_ok": None,
                "notes": "",
            }
        )
        print(f"  ether_ok={ok} ms={ms}", flush=True)

    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_dir = ROOT / "memory" / "bench"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"compare_{day}.md"
    lines = [
        f"# Side-by-side compare {day}",
        "",
        "Fill peer columns manually after running the same tasks in other tools.",
        "",
        "| Task | ETHER | ms | conf | Aider | Continue | Cursor | notes |",
        "|------|------:|---:|-----:|------:|---------:|-------:|-------|",
    ]
    for row in rows:
        lines.append(
            f"| {row['id']} | {row['ether_ok']} | {row['ether_ms']} | {row['confidence']} |  |  |  |  |"
        )
    lines.append("")
    lines.append(f"_Generated in {round(time.perf_counter()-t0,1)}s_")
    path.write_text("\n".join(lines), encoding="utf-8")
    (out_dir / f"compare_{day}.json").write_text(json.dumps({"rows": rows}, indent=2), encoding="utf-8")
    print(json.dumps({"path": str(path), "n": len(rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
