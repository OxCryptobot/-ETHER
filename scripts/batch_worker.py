#!/usr/bin/env python3
"""Process next items from memory/batch_queue.json via Pipeline."""

from __future__ import annotations

import json
import subprocess
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
PY = sys.executable


def load_queue() -> dict:
    if not QUEUE.exists():
        return {"pending": [], "done": []}
    return json.loads(QUEUE.read_text(encoding="utf-8"))


def save_queue(data: dict) -> None:
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    QUEUE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def normalize_command(cmd: list) -> list[str]:
    """Rewrite leading 'python' to this venv interpreter."""
    if not cmd:
        return []
    out = [str(x) for x in cmd]
    if out[0] in ("python", "python3", "py"):
        out[0] = PY
    return out


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
    data.setdefault("done", []).append({**item, "result": result})
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
