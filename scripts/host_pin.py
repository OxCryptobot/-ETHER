"""Last-good commit and rollback pin for the host writer (batch 5). Local only, never pushed.

State lives inside the git dir (.git/ether_host_good, .git/ether_host_pin.json): never
tracked, never stashed, never published.

- record_good(base, sha): the supervisor's post-pull smoke passed on sha.
- rollback(base, good, bad): ETHER_PULL_ROLLBACK=1 only. `git reset --keep good` (refuses
  instead of discarding local changes; never --hard) and pin `bad`.
- pinned(base): while pinned the supervisor does not fast-forward onto a tip whose code
  equals the bad commit's (artifact-only commits do not count), host_main skips its sync
  pull, and publish goes out through the origin/main worktree (no local rebase onto bad).
  A new upstream code change clears the pin and is smoke-tested again.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

GOOD = "ether_host_good"
PIN = "ether_host_pin.json"


def rollback_enabled() -> bool:
    return os.getenv("ETHER_PULL_ROLLBACK", "0") == "1"


def _gitdir(base: Path) -> Optional[Path]:
    d = Path(base) / ".git"
    if d.is_dir():
        return d
    if d.is_file():  # worktree: "gitdir: <path>"
        try:
            txt = d.read_text(encoding="utf-8").strip()
            if txt.startswith("gitdir:"):
                return Path(txt.split(":", 1)[1].strip())
        except OSError:
            return None
    return None


def last_good(base: Path) -> str:
    d = _gitdir(base)
    try:
        return (d / GOOD).read_text(encoding="utf-8").strip() if d else ""
    except OSError:
        return ""


def record_good(base: Path, sha: str) -> None:
    d = _gitdir(base)
    if d and sha:
        (d / GOOD).write_text(sha + "\n", encoding="utf-8")


def pin(base: Path) -> Dict[str, Any]:
    d = _gitdir(base)
    try:
        return json.loads((d / PIN).read_text(encoding="utf-8")) if d else {}
    except (OSError, ValueError):
        return {}


def pinned(base: Path) -> bool:
    return bool(pin(base).get("bad"))


def set_pin(base: Path, row: Dict[str, Any]) -> None:
    d = _gitdir(base)
    if d:
        (d / PIN).write_text(json.dumps(row, indent=1) + "\n", encoding="utf-8")


def clear_pin(base: Path) -> None:
    d = _gitdir(base)
    if d:
        try:
            (d / PIN).unlink()
        except OSError:
            pass


Runner = Callable[[List[str]], subprocess.CompletedProcess]


def code_moved_since(run: Runner, git: str, bad: str, ref: str = "origin/main") -> bool:
    """True when ref has a non-artifact change relative to the bad commit."""
    p = run([git, "diff", "--quiet", bad, ref, "--", ".", ":(exclude)artifacts"])
    return p.returncode == 1


def rollback(base: Path, run: Runner, git: str, good: str, bad: str, smoke: Dict[str, Any]) -> Dict[str, Any]:
    if not good or good == bad:
        return {"ok": False, "note": "no_last_good"}
    p = run([git, "reset", "--keep", good])
    row = {"ok": p.returncode == 0, "good": good, "bad": bad, "rc": p.returncode,
           "stderr": (p.stderr or "")[-200:]}
    if row["ok"]:
        broken = (smoke.get("imports") or {}).get("broken") or (smoke.get("compile") or {}).get("bad") or []
        set_pin(base, {"bad": bad, "good": good, "ts": datetime.now(timezone.utc).isoformat(),
                       "why": list(broken)[:5] or [str(smoke.get("error") or "smoke failed")]})
    return row
