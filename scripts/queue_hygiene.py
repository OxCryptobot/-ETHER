"""Once-and-for-all queue hygiene.

Why failed jobs keep coming back: host archives locally, then
`git reset --hard origin/main` restores artifacts/jobs/failed/*.json from GitHub.
Why done looks empty: thousands of playbook_timeout_revise / ss_* files bury real jobs.
Why pending is empty: host is idle after drain — not dead.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
FAILED = ROOT / "artifacts" / "jobs" / "failed"
DONE = ROOT / "artifacts" / "jobs" / "done"
ARCH = ROOT / "artifacts" / "jobs" / "failed_archived"
OUT = ROOT / "artifacts" / "queue_hygiene.json"

NOISE_PREFIX = (
    "playbook_",
    "ss_archive_",
    "ss_direct_hard_",
    "ss_pipeline_ledger_",
    "ss_tool_runtime_",
    "ss_pipeline_scripted_",
    "recover_",
)


def _noise(name: str) -> bool:
    return name.startswith(NOISE_PREFIX)


def archive_failed() -> int:
    ARCH.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in list(FAILED.glob("*.json")):
        shutil.move(str(p), str(ARCH / p.name))
        n += 1
    return n


def prune_done_noise(keep_recent: int = 40) -> int:
    files = sorted(DONE.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    n = 0
    kept = 0
    for p in files:
        if _noise(p.name):
            p.unlink(missing_ok=True)
            n += 1
            continue
        kept += 1
        if kept > keep_recent:
            p.unlink(missing_ok=True)
            n += 1
    return n


def untrack() -> str:
    cmds = [
        ["git", "rm", "-r", "--cached", "--ignore-unmatch", "artifacts/jobs/failed"],
        ["git", "rm", "-r", "--cached", "--ignore-unmatch", "artifacts/jobs/done"],
    ]
    notes: List[str] = []
    for cmd in cmds:
        try:
            r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=60)
            notes.append((r.stdout or r.stderr or "")[:200])
        except Exception as exc:
            notes.append(str(exc)[:200])
    return " | ".join(notes)


def main() -> int:
    moved = archive_failed()
    pruned = prune_done_noise()
    git_note = untrack()
    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "archived_failed": moved,
        "pruned_done_noise": pruned,
        "git_rm_cached": git_note[:400],
        "note": (
            "failed JSON must not live on origin. reset --hard was resurrecting them. "
            "Dashboard should read last_job + pending only for 'what is happening'."
        ),
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
