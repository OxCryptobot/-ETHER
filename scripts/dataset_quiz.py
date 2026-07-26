#!/usr/bin/env python3
"""Run MBPP-lite + hidden HumanEval-style with signature-only prompts."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.dotenv import load_dotenv
from core.pipeline import Pipeline
from core.schemas import Envelope, ClearQuartzRequest
from core.registry import build_default_registry
from core.scoreboard import write_scoreboard
from core.health_metric import compute_health

load_dotenv(ROOT / ".env")


def _load_tasks(limit: int) -> list:
    tasks = []
    for path in (
        ROOT / "memory" / "quizzes" / "hidden_humaneval.json",
        ROOT / "memory" / "datasets" / "mbpp_lite.json",
    ):
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for t in data.get("tasks") or []:
            tasks.append(t)
    return tasks[:limit]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=12)
    args = ap.parse_args()
    tasks = _load_tasks(args.limit)
    pipe = Pipeline()
    reg = build_default_registry()
    rows = []
    t0 = time.perf_counter()
    for i, t in enumerate(tasks, 1):
        tid = t.get("id")
        prompt = t.get("prompt") or t.get("objective")
        hidden = t.get("hidden_test") or ""
        print(f"[dataset {i}/{len(tasks)}] {tid}", flush=True)
        r = pipe.run(prompt)
        code = (r.generated_code or "").rstrip()
        combined = code + ("\n\n# hidden\n" + hidden if hidden else "\n")
        sand = reg.execute(
            Envelope(
                task_id=uuid4(),
                target_gem="clear-quartz",
                payload=ClearQuartzRequest(code=combined),
                timeout_seconds=60,
            )
        )
        ok = not sand.error and getattr(sand.payload, "exit_code", 1) == 0
        rows.append({"id": tid, "ok": ok, "conf": r.confidence})
        print(f"  ok={ok}", flush=True)

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kind": "dataset_hidden",
        "n": len(rows),
        "pass": sum(1 for x in rows if x["ok"]),
        "pass_rate": round(sum(1 for x in rows if x["ok"]) / max(1, len(rows)), 3),
        "duration_s": round(time.perf_counter() - t0, 2),
        "results": rows,
    }
    out = ROOT / "memory" / "quiz"
    out.mkdir(parents=True, exist_ok=True)
    (out / "dataset_latest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    # feed health via quiz timestamp if no holdout yet
    if not (out / "latest.json").exists():
        (out / "latest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    compute_health()
    write_scoreboard()
    print(json.dumps({k: summary[k] for k in ("n", "pass", "pass_rate")}, indent=2))
    return 0 if summary["pass"] == summary["n"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
