#!/usr/bin/env python3
"""Hidden-test quiz: model sees signature only; asserts concatenated post-generation."""

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
from core.health_metric import compute_health
from core.scoreboard import write_scoreboard

load_dotenv(ROOT / ".env")

HIDDEN = ROOT / "memory" / "quizzes" / "hidden_humaneval.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()

    data = json.loads(HIDDEN.read_text(encoding="utf-8"))
    tasks = list(data.get("tasks") or [])[: args.limit]
    pipe = Pipeline()
    rows = []
    t0 = time.perf_counter()
    for i, t in enumerate(tasks, 1):
        print(f"[hidden {i}/{len(tasks)}] {t['id']} ...", flush=True)
        # generate from signature-only prompt
        r = pipe.run(t["prompt"])
        code = r.generated_code or ""
        # re-test with hidden asserts if generation exited sandbox already
        # stronger: concatenate and re-sandbox via Clear Quartz only
        from core.schemas import Envelope, ClearQuartzRequest
        from core.registry import build_default_registry
        from uuid import uuid4

        combined = code.rstrip() + "\n\n# hidden tests\n" + t["hidden_test"] + "\n"
        reg = build_default_registry()
        sand = reg.execute(
            Envelope(
                task_id=uuid4(),
                target_gem="clear-quartz",
                payload=ClearQuartzRequest(code=combined),
                timeout_seconds=60,
            )
        )
        ok = (
            not sand.error
            and sand.payload is not None
            and getattr(sand.payload, "exit_code", 1) == 0
        )
        rows.append(
            {
                "id": t["id"],
                "gen_status": r.status,
                "hidden_ok": ok,
                "exit": getattr(sand.payload, "exit_code", None) if not sand.error else None,
                "confidence": r.confidence,
            }
        )
        print(f"  hidden_ok={ok}", flush=True)

    passed = sum(1 for x in rows if x["hidden_ok"])
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kind": "hidden_humaneval",
        "n": len(rows),
        "pass": passed,
        "pass_rate": round(passed / max(1, len(rows)), 3),
        "duration_s": round(time.perf_counter() - t0, 2),
        "results": rows,
    }
    out = ROOT / "memory" / "quiz"
    out.mkdir(parents=True, exist_ok=True)
    (out / "hidden_latest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    # also refresh quiz latest if better to keep health green path optional
    compute_health()
    try:
        write_scoreboard()
    except Exception:
        pass
    print(json.dumps({k: summary[k] for k in ("n", "pass", "pass_rate", "duration_s")}, indent=2))
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
