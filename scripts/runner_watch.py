"""If the GitHub runner process is gone, start it. No git, no window."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def needs_start(tasklist_text: str) -> bool:
    return "Runner.Listener.exe" not in (tasklist_text or "")


def watch() -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "os": os.name,
        "ok": True,
    }
    if os.name != "nt":
        row["note"] = "observe_only"
        return row
    flags = 0x08000000
    try:
        listed = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Runner.Listener.exe", "/NH"],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=flags,
        )
        text = listed.stdout or ""
    except Exception as exc:
        text = ""
        row["list_error"] = type(exc).__name__
    row["listener"] = not needs_start(text)
    if needs_start(text):
        from scripts.start_runner import start_runner

        row["start"] = start_runner()
        row["ok"] = bool(row["start"].get("ok"))
        row["note"] = "started" if row["ok"] else "start_failed"
    else:
        row["note"] = "listener_up"
    art = ROOT / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    (art / "runner_watch.json").write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    return row


if __name__ == "__main__":
    print(json.dumps(watch()))
