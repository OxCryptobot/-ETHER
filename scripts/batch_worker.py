#!/usr/bin/env python3
"""Process items from memory/batch_queue.json via Pipeline or command."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.dotenv import load_dotenv
from core.batch_queue import (
    load_queue,
    save_queue,
    append_history,
    status as queue_status,
    seed_smoke,
)
from core.pipeline import Pipeline

load_dotenv(ROOT / ".env")

PY = sys.executable


def normalize_command(cmd: list) -> list[str]:
    """Rewrite leading 'python' to this venv interpreter."""
    if not cmd:
        return []
    out = [str(x) for x in cmd]
    if out[0] in ("python", "python3", "py"):
        out[0] = PY
    return out


def process_one(item: dict) -> dict:
    kind = item.get("kind", "pipeline")
    title = item.get("title", "")
    objective = item.get("objective", "")
    print(f"[batch] {title} kind={kind}", flush=True)

    result: dict = {
        "title": title,
        "kind": kind,
        "id": item.get("id"),
        "started": datetime.now(timezone.utc).isoformat(),
        "ok": False,
    }

    try:
        if kind == "pipeline" and objective:
            r = Pipeline().run(objective)
            ok = r.status == "complete" and bool(r.sandbox and r.sandbox.exit_code == 0)
            result.update(
                {
                    "ok": ok,
                    "status": r.status,
                    "confidence": round(float(r.confidence or 0), 4),
                    "verification_score": round(float(r.verification_score or 0), 4),
                    "execution_score": round(float(r.execution_score or 0), 4),
                    "exit_code": r.sandbox.exit_code if r.sandbox else None,
                    "total_tests": int(r.sandbox.total_tests) if r.sandbox else 0,
                    "used_burst": bool(r.used_burst),
                    "retries": int(r.retries),
                    "strategy": r.strategy,
                    "error": r.error,
                }
            )
        elif kind == "command":
            cmd = normalize_command(item.get("command") or [])
            if not cmd:
                result["error"] = "empty command"
            else:
                p = subprocess.run(cmd, cwd=str(ROOT))
                result["ok"] = p.returncode == 0
                result["returncode"] = p.returncode
                result["command"] = cmd
        else:
            result["error"] = "unsupported or empty item"
    except Exception as e:
        result["error"] = str(e)[:300]

    result["finished"] = datetime.now(timezone.utc).isoformat()
    return result


def drain(limit: int = 1) -> dict:
    data = load_queue()
    pending = list(data.get("pending") or [])
    if not pending:
        return {"ok": True, "processed": 0, "message": "queue empty", "results": []}

    n = max(1, min(limit, len(pending)))
    results = []
    for _ in range(n):
        if not pending:
            break
        item = pending.pop(0)
        result = process_one(item)
        data.setdefault("done", []).append({**item, "result": result})
        append_history(result)
        results.append(result)

    data["done"] = data["done"][-200:]
    data["pending"] = pending
    save_queue(data)

    ok_n = sum(1 for r in results if r.get("ok"))
    return {
        "ok": ok_n == len(results),
        "processed": len(results),
        "passed": ok_n,
        "failed": len(results) - ok_n,
        "remaining": len(pending),
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="@ETHER batch worker")
    parser.add_argument("--limit", type=int, default=1, help="Max items to process this run")
    parser.add_argument("--status", action="store_true", help="Print queue status and exit")
    parser.add_argument("--seed", action="store_true", help="Seed smoke tasks if empty")
    parser.add_argument("--seed-force", action="store_true", help="Force re-seed smokes")
    parser.add_argument("--json", action="store_true", help="JSON only")
    args = parser.parse_args(argv)

    if args.status:
        st = queue_status()
        print(json.dumps(st, indent=2))
        return 0

    if args.seed or args.seed_force:
        out = seed_smoke(force=args.seed_force)
        print(json.dumps(out, indent=2))
        if not args.limit or args.limit <= 0:
            return 0 if out.get("ok") else 1

    report = drain(limit=max(1, args.limit))
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
