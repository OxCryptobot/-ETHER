#!/usr/bin/env python3
"""Process next items from memory/batch_queue.json via Pipeline.

Local autonomy path for 'build next features' without the chat:
  - queue holds objectives / maintenance tasks
  - worker runs one pending item per tick
  - results appended to memory/batch_queue/history.jsonl
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.dotenv import load_dotenv
from core.pipeline import Pipeline

load_dotenv(ROOT / ".env")

QUEUE = ROOT / "memory" / "batch_queue.json"
HIST = ROOT / "memory" / "batch_queue" / "history.jsonl"


def load_queue() -> dict:
    if not QUEUE.exists():
        return {"pending": [], "done": []}
    return json.loads(QUEUE.read_text(encoding="utf-8"))


def save_queue(data: dict) -> None:
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    QUEUE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> int:
    data = load_queue()
    pending = data.get("pending") or []
    if not pending:
        print(json.dumps({"ok": True, "message": "queue empty"}))
        return 0

    item = pending.pop(0)
    kind = item.get("kind", "pipeline")
    title = item.get("title", "")
    objective = item.get("objective", "")
    print(f"[batch] {title} kind={kind}", flush=True)

    result = {
        "title": title,
        "kind": kind,
        "started": datetime.now(timezone.utc).isoformat(),
        "ok": False,
    }

    try:
        if kind == "pipeline" and objective:
            r = Pipeline().run(objective)
            result.update(
                {
                    "ok": r.status == "complete" and bool(r.sandbox and r.sandbox.exit_code == 0),
                    "status": r.status,
                    "confidence": r.confidence,
                    "exit_code": r.sandbox.exit_code if r.sandbox else None,
                }
            )
        elif kind == "command":
            import subprocess

            cmd = item.get("command") or []
            p = subprocess.run(cmd, cwd=str(ROOT))
            result["ok"] = p.returncode == 0
            result["returncode"] = p.returncode
        else:
            result["error"] = "unsupported or empty item"
    except Exception as e:
        result["error"] = str(e)[:300]

    result["finished"] = datetime.now(timezone.utc).isoformat()
    data.setdefault("done", []).append({**item, "result": result})
    # keep done list bounded
    data["done"] = data["done"][-100:]
    data["pending"] = pending
    save_queue(data)

    HIST.parent.mkdir(parents=True, exist_ok=True)
    with HIST.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result) + "\n")

    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
