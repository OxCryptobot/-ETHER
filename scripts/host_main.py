"""Disk writer kernel. Frozen exe must import this each cycle."""
from __future__ import annotations
import json, os, subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

def _root() -> Path:
    env = os.environ.get("ETHER_ROOT")
    if env and (Path(env) / "scripts").is_dir():
        return Path(env).resolve()
    win = Path(r"C:\Users\Otcde\ETHER")
    if (win / "scripts").is_dir():
        return win.resolve()
    return Path(__file__).resolve().parents[1]

def _git() -> str:
    for p in (r"C:\Program Files\Git\cmd\git.exe", r"C:\Program Files (x86)\Git\cmd\git.exe"):
        if Path(p).is_file():
            return p
    return "git"

def _pull(root: Path) -> None:
    if os.name != "nt":
        return
    kw: Dict[str, Any] = {"cwd": str(root), "timeout": 120, "capture_output": True, "creationflags": 0x08000000}
    git = _git()
    try:
        subprocess.run([git, "fetch", "origin"], **kw)
        pull = subprocess.run([git, "pull", "--ff-only", "origin", "main"], **kw)
        if pull.returncode != 0:
            subprocess.run([git, "reset", "--hard", "origin/main"], **kw)
    except Exception:
        return

def tick() -> Dict[str, Any]:
    root = _root()
    os.environ["ETHER_ROOT"] = str(root)
    row: Dict[str, Any] = {"ts": datetime.now(timezone.utc).isoformat(), "root": str(root), "os": os.name}
    if os.name == "nt":
        _pull(root)
        try:
            from scripts.app_keepalive import ensure_keepalive
            row["keepalive"] = ensure_keepalive(root)
        except Exception as exc:
            row["keepalive_error"] = type(exc).__name__
        try:
            from scripts.exe_pulse import pulse
            row["pulse"] = pulse(push=True)
        except Exception as exc:
            row["pulse_error"] = type(exc).__name__
        try:
            from scripts.origin_publish import publish
            row["publish"] = publish(root, message="1650 host_main")
        except Exception as exc:
            row["publish_error"] = type(exc).__name__
    else:
        row["note"] = "observe_only"
    art = root / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    (art / "host_main.json").write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    return row
