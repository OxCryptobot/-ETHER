#!/usr/bin/env python3
"""ETHER Host - ONE window: dashboard + job agent + foreman.

    .\.venv\Scripts\python.exe scripts\ether_host.py

Dashboard: http://127.0.0.1:8787/agent

Auto-reload: if origin moves HEAD (new commits that touch host scripts),
the process exits with code 42 so start_ether_host.ps1 restarts it.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

try:
    from core.dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass

_WATCHED_REL = (
    "scripts/ether_host.py",
    "scripts/host_agent.py",
    "scripts/foreman.py",
)


def _run_git(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _head_sha() -> str:
    r = _run_git(["rev-parse", "HEAD"])
    if r.returncode != 0:
        return ""
    return (r.stdout or "").strip()


def _scripts_changed_since(old_sha: str) -> bool:
    """True only if HEAD moved AND one of the watched scripts is in the diff."""
    if not old_sha:
        return False
    new_sha = _head_sha()
    if not new_sha or new_sha == old_sha:
        return False
    r = _run_git(["diff", "--name-only", f"{old_sha}..{new_sha}", "--", *_WATCHED_REL])
    if r.returncode != 0:
        return False
    changed = {line.strip().replace("\\", "/") for line in (r.stdout or "").splitlines() if line.strip()}
    return any(w in changed for w in _WATCHED_REL)


def _start_dashboard() -> None:
    import uvicorn

    uvicorn.run("dashboard.app:app", host="127.0.0.1", port=8787, log_level="warning", reload=False)


def main() -> int:
    print("=" * 60, flush=True)
    print("  ETHER HOST - single window", flush=True)
    print("  dashboard  http://127.0.0.1:8787/agent", flush=True)
    print("  agent      job consumer", flush=True)
    print("  foreman    apprentice curriculum", flush=True)
    print("  auto-reload on script change (exit 42)", flush=True)
    print("=" * 60, flush=True)

    t = threading.Thread(target=_start_dashboard, name="dashboard", daemon=True)
    t.start()
    time.sleep(1.2)

    from scripts import foreman
    import scripts.host_agent as agent

    agent.git_reset_to_origin("ether_host startup")
    agent.PENDING.mkdir(parents=True, exist_ok=True)
    agent.DONE.mkdir(parents=True, exist_ok=True)
    agent.FAILED.mkdir(parents=True, exist_ok=True)

    baseline_sha = _head_sha()
    agent.log(f"boot HEAD={baseline_sha[:10] if baseline_sha else '?'}")

    fr = foreman.tick()
    agent.log(f"foreman boot: {fr}")

    while True:
        try:
            agent.write_status(current_job=None, phase="polling")
            agent.git_sync()

            if _scripts_changed_since(baseline_sha):
                agent.log("host scripts updated on origin - exiting for clean reload (code 42)")
                agent.write_status(phase="reloading", note="scripts changed")
                return 42

            fr = foreman.tick()
            if fr.get("enqueued") or fr.get("playbook"):
                agent.log(f"foreman: {fr}")

            jobs = agent.list_pending()
            if not jobs:
                agent.log("idle")
                agent.write_status(
                    current_job=None,
                    phase="idle",
                    foreman=foreman.status(),
                )
                time.sleep(max(1, agent.POLL))
                continue

            for job_path in jobs:
                agent.process_job(job_path)
                agent.git_sync()
                if _scripts_changed_since(baseline_sha):
                    agent.log("host scripts updated on origin - exiting for clean reload (code 42)")
                    agent.write_status(phase="reloading", note="scripts changed")
                    return 42
                fr = foreman.tick()
                if fr.get("enqueued") or fr.get("playbook"):
                    agent.log(f"foreman: {fr}")
        except KeyboardInterrupt:
            agent.log("stop")
            agent.write_status(phase="stopped")
            return 0
        except Exception as e:
            agent.log(f"loop error: {e}")
            try:
                agent.git_sync()
            except Exception:
                pass
            time.sleep(max(1, agent.POLL))


if __name__ == "__main__":
    raise SystemExit(main())
