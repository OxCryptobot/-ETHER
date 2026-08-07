#!/usr/bin/env python3
"""ETHER host agent — pull jobs from origin, run, push reports.

Architecture
------------
Grok (or any operator) writes a job file to the repo:

    artifacts/jobs/pending/<id>.json

This agent (running on the Windows host) every POLL seconds:

1. git fetch + merge origin/main (soft)
2. picks the oldest pending job
3. runs its steps (or a named sprint via host_runner)
4. writes artifacts/host_report_latest.md + .json
5. moves job to artifacts/jobs/done/
6. git add/commit/push the report + done marker

Start once:

    .\.venv\Scripts\python.exe scripts\host_agent.py

Leave it running. After that Grok only pushes jobs — no manual paste.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

try:
    from core.dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass

POLL = int(os.getenv("ETHER_HOST_AGENT_POLL", "20"))
PY = sys.executable
PENDING = ROOT / "artifacts" / "jobs" / "pending"
DONE = ROOT / "artifacts" / "jobs" / "done"
FAILED = ROOT / "artifacts" / "jobs" / "failed"
LOG = ROOT / "memory" / "host_agent" / "agent.log"


def log(msg: str) -> None:
    line = f"[{datetime.now(timezone.utc).isoformat()}] {msg}"
    print(line, flush=True)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def run(cmd: List[str], timeout: int = 3600) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def git_pull_soft() -> None:
    run(["git", "fetch", "origin"], timeout=120)
    # Prefer merge to keep local wired files if any; fall back to reset only if clean jobs dir policy
    r = run(["git", "merge", "--ff-only", "origin/main"], timeout=60)
    if r.returncode != 0:
        log(f"ff-only failed; leaving local tree (rc={r.returncode})")


def git_push_report(job_id: str, ok: bool) -> None:
    paths = [
        "artifacts/host_report_latest.md",
        "artifacts/host_report_latest.json",
    ]
    # include stamped reports if present
    art = ROOT / "artifacts"
    if art.exists():
        for p in art.glob("host_report_*.md"):
            paths.append(str(p.relative_to(ROOT)))
        for p in art.glob("host_report_*.json"):
            paths.append(str(p.relative_to(ROOT)))
    for rel in ("artifacts/jobs/done", "artifacts/jobs/failed"):
        d = ROOT / rel
        if d.exists():
            for p in d.glob("*"):
                paths.append(str(p.relative_to(ROOT)))

    run(["git", "add", "-f", "--"] + paths, timeout=60)
    status = "PASS" if ok else "FAIL"
    msg = f"host agent report: job={job_id} {status}"
    c = run(["git", "commit", "-m", msg], timeout=60)
    if c.returncode != 0 and "nothing to commit" in (c.stdout + c.stderr):
        log("nothing to commit")
        return
    p = run(["git", "push", "origin", "main"], timeout=120)
    log(f"push rc={p.returncode}")


def list_pending() -> List[Path]:
    PENDING.mkdir(parents=True, exist_ok=True)
    jobs = sorted(PENDING.glob("*.json"), key=lambda p: p.stat().st_mtime)
    return jobs


def run_sprint(name: str) -> int:
    runner = ROOT / "scripts" / "host_runner.ps1"
    if not runner.exists():
        log("host_runner.ps1 missing")
        return 2
    # PowerShell Bypass so execution policy never blocks agent
    ps = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(runner),
        "-Sprint",
        name,
        # agent itself commits; do not double-push from runner
    ]
    log(f"sprint {name}")
    r = run(ps, timeout=7200)
    if r.stdout:
        print(r.stdout[-4000:], flush=True)
    if r.stderr:
        print(r.stderr[-2000:], flush=True)
    return r.returncode


def run_steps(steps: List[Dict[str, Any]]) -> int:
    """Each step: {"cmd": "..."} or {"argv": ["python", "-m", ...]}."""
    for i, step in enumerate(steps, 1):
        argv = step.get("argv")
        cmd = step.get("cmd")
        log(f"step {i}/{len(steps)}: {argv or cmd}")
        if argv:
            r = run([str(x) for x in argv], timeout=int(step.get("timeout", 3600)))
        elif cmd:
            r = run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd], timeout=int(step.get("timeout", 3600)))
        else:
            log("empty step")
            return 2
        if r.stdout:
            print(r.stdout[-3000:], flush=True)
        if r.stderr:
            print(r.stderr[-1500:], flush=True)
        if r.returncode != 0:
            log(f"step failed rc={r.returncode}")
            return r.returncode
    return 0


def process_job(path: Path) -> bool:
    try:
        job = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"bad job json: {e}")
        FAILED.mkdir(parents=True, exist_ok=True)
        path.rename(FAILED / path.name)
        return False

    job_id = job.get("id") or path.stem
    log(f"JOB START {job_id}")
    ok = False
    rc = 1
    try:
        if job.get("sprint"):
            rc = run_sprint(str(job["sprint"]))
        elif job.get("steps"):
            rc = run_steps(list(job["steps"]))
        else:
            log("job has neither sprint nor steps")
            rc = 2
        ok = rc == 0
    except Exception as e:
        log(f"job exception: {e}")
        ok = False

    # write a minimal agent envelope alongside host_runner reports
    art = ROOT / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    envelope = {
        "job_id": job_id,
        "ok": ok,
        "rc": rc,
        "finished": datetime.now(timezone.utc).isoformat(),
        "sprint": job.get("sprint"),
    }
    (art / "host_agent_last_job.json").write_text(json.dumps(envelope, indent=2), encoding="utf-8")

    dest_dir = DONE if ok else FAILED
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / path.name
    if dest.exists():
        dest = dest_dir / f"{path.stem}_{int(time.time())}.json"
    path.rename(dest)
    log(f"JOB END {job_id} ok={ok}")
    try:
        git_push_report(job_id, ok)
    except Exception as e:
        log(f"push error: {e}")
    return ok


def main() -> int:
    print("=" * 60, flush=True)
    print("  ETHER host_agent — job queue consumer", flush=True)
    print(f"  root={ROOT}", flush=True)
    print(f"  poll={POLL}s  pending={PENDING}", flush=True)
    print("=" * 60, flush=True)
    PENDING.mkdir(parents=True, exist_ok=True)
    DONE.mkdir(parents=True, exist_ok=True)
    FAILED.mkdir(parents=True, exist_ok=True)

    while True:
        try:
            git_pull_soft()
            jobs = list_pending()
            if not jobs:
                log("idle")
            for job_path in jobs:
                process_job(job_path)
        except KeyboardInterrupt:
            log("stop")
            return 0
        except Exception as e:
            log(f"loop error: {e}")
        time.sleep(max(5, POLL))


if __name__ == "__main__":
    raise SystemExit(main())
