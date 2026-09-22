"""Publish 1650 artifacts to origin. Never silent. Ubuntu no-ops."""
from __future__ import annotations
import json, os, subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

PATHS = [
    "artifacts/host_attach.json",
    "artifacts/app_alive.json",
    "artifacts/ollama_probe.json",
    "artifacts/exe_pulse.json",
    "artifacts/git_push.json",
    "artifacts/week_tick.json",
    "artifacts/autonomy_tick.json",
    "artifacts/self_state.json",
    "artifacts/gem_energy.json",
    "artifacts/jobs",
]

def _git() -> str:
    for p in (r"C:\Program Files\Git\cmd\git.exe", r"C:\Program Files (x86)\Git\cmd\git.exe"):
        if Path(p).is_file():
            return p
    return "git"

def publish(root: Path, *, message: str = "1650 exe pulse") -> Dict[str, Any]:
    root = Path(root)
    art = root / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    row: Dict[str, Any] = {"ts": datetime.now(timezone.utc).isoformat(), "os": os.name, "ok": False}
    if os.name != "nt" or "Otcde" not in str(root):
        row["note"] = "observe_only"
        (art / "git_push.json").write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
        return row
    git = _git()
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    kw: Dict[str, Any] = {"cwd": str(root), "timeout": 120, "capture_output": True, "text": True, "env": env, "creationflags": 0x08000000}
    def run(argv: List[str]) -> subprocess.CompletedProcess:
        return subprocess.run(argv, **kw)
    try:
        run([git, "add", *PATHS])
        diff = run([git, "diff", "--cached", "--quiet"])
        if diff.returncode == 0:
            row.update({"ok": True, "note": "no_change"})
        else:
            c = run([git, "-c", "user.email=ether@local", "-c", "user.name=ether-exe", "commit", "-m", message])
            p = run([git, "push", "origin", "main"])
            row.update({
                "ok": p.returncode == 0,
                "commit_rc": c.returncode,
                "push_rc": p.returncode,
                "stderr": ((p.stderr or "") + (c.stderr or ""))[-400:],
            })
    except Exception as exc:
        row["error"] = type(exc).__name__
    (art / "git_push.json").write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    return row
