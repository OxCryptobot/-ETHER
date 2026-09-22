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
    if run.is_file() and not row.get("ok"):
        try:
            subprocess.Popen(
                ["cmd.exe", "/c", str(run)],
                cwd=str(run.parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
            )
            row["spawned_run_cmd"] = True
            row["ok"] = True
        except Exception as exc:
            row["spawn_error"] = type(exc).__name__
    return row
