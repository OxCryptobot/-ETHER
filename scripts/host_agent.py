#!/usr/bin/env python3
"""ETHER host agent — pull jobs from origin, run, push reports.

Start once and leave running:

    .\.venv\Scripts\python.exe scripts\host_agent.py

Dashboard: http://127.0.0.1:8787/agent  (start via scripts/start_agent_stack.ps1)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

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
STATUS = ROOT / "memory" / "host_agent" / "status.json"


def log(msg: str) -> None:
    line = f"[{datetime.now(timezone.utc).isoformat()}] {msg}"
    print(line, flush=True)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def write_status(**extra: Any) -> None:
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "heartbeat": datetime.now(timezone.utc).isoformat(),
        "poll_s": POLL,
        "root": str(ROOT),
        **extra,
    }
    try:
        STATUS.write_text(json.dumps(payload, indent=2), encoding="utf-8")
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
    r = run(["git", "merge", "--ff-only", "origin/main"], timeout=60)
    if r.returncode != 0:
        log(f"ff-only failed; leaving local tree (rc={r.returncode})")


def git_push_report(job_id: str, ok: bool) -> None:
    paths = [
        "artifacts/host_report_latest.md",
        "artifacts/host_report_latest.json",
        "artifacts/host_agent_last_job.json",
        "memory/host_agent/status.json",
    ]
    art = ROOT / "artifacts"
    if art.exists():
        for p in art.glob("host_report_*.md"):
            paths.append(str(p.relative_to(ROOT)))
        for p in art.glob("host_report_*.json"):
            paths.append(str(p.relative_to(ROOT)))
    for rel in ("artifacts/jobs/done", "artifacts/jobs/failed"):
        d = ROOT / rel
        if d.exists():
            for p in d.glob("*.json"):
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
    return sorted(PENDING.glob("*.json"), key=lambda p: p.stat().st_mtime)


def run_sprint(name: str) -> int:
    runner = ROOT / "scripts" / "host_runner.ps1"
    if not runner.exists():
        log("host_runner.ps1 missing")
        return 2
    ps = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(runner),
        "-Sprint",
        name,
    ]
    log(f"sprint {name}")
    r = run(ps, timeout=7200)
    if r.stdout:
        print(r.stdout[-4000:], flush=True)
    if r.stderr:
        print(r.stderr[-2000:], flush=True)
    return r.returncode


def run_steps(steps: List[Dict[str, Any]]) -> int:
    for i, step in enumerate(steps, 1):
        argv = step.get("argv")
        cmd = step.get("cmd")
        log(f"step {i}/{len(steps)}: {argv or cmd}")
        if argv:
            r = run([str(x) for x in argv], timeout=int(step.get("timeout", 3600)))
        elif cmd:
            r = run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                timeout=int(step.get("timeout", 3600)),
            )
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
    write_status(current_job=job_id, phase="running")
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
    write_status(current_job=None, phase="idle", last_job=job_id, last_ok=ok)
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
    print("  dashboard: http://127.0.0.1:8787/agent", flush=True)
    print("=" * 60, flush=True)
    PENDING.mkdir(parents=True, exist_ok=True)
    DONE.mkdir(parents=True, exist_ok=True)
    FAILED.mkdir(parents=True, exist_ok=True)

    while True:
        try:
            write_status(current_job=None, phase="polling")
            git_pull_soft()
            jobs = list_pending()
            if not jobs:
                log("idle")
            for job_path in jobs:
                process_job(job_path)
        except KeyboardInterrupt:
            log("stop")
            write_status(phase="stopped")
            return 0
        except Exception as e:
            log(f"loop error: {e}")
        time.sleep(max(5, POLL))


if __name__ == "__main__":
    raise SystemExit(main())
