"""Start the existing GitHub runner on the 1650. No operator shell."""
from __future__ import annotations
import os, subprocess
from pathlib import Path
from typing import Any, Dict

def start_runner() -> Dict[str, Any]:
    if os.name != "nt":
        return {"ok": True, "note": "observe_only"}
    flags = 0x08000000
    row: Dict[str, Any] = {"ok": False}
    try:
        r = subprocess.run(
            ["schtasks", "/Run", "/TN", "ETHER-Runner"],
            capture_output=True, text=True, timeout=20, creationflags=flags,
        )
        row["task_rc"] = r.returncode
        row["ok"] = r.returncode == 0
    except Exception as exc:
        row["task_error"] = type(exc).__name__
    run = Path(os.environ.get("ETHER_RUNNER_DIR") or r"C:\actions-runner") / "run.cmd"
    listener = run.parent / "bin" / "Runner.Listener.exe"
    if not row.get("ok") and (listener.is_file() or run.is_file()):
        try:
            from scripts.win_quiet import popen_hidden
            argv = [str(listener), "run"] if listener.is_file() else ["cmd.exe", "/c", str(run)]
            popen_hidden(argv, cwd=str(run.parent))
            row["spawned_hidden"] = True
            row["ok"] = True
        except Exception as exc:
            row["spawn_error"] = type(exc).__name__
    return row
