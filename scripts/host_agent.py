#!/usr/bin/env python3
"""ETHER host agent — job queue consumer.

Git policy (never stuck):
  - On startup: fetch + reset --hard origin/main
  - Each poll: fetch + ff-only; if diverged, reset --hard origin/main
  - Push report: stage the jobs directories + status files (git handles add+delete)
  - Never expand every historical file into argv (that caused WinError 206)
  - On push fail: one rebase retry then hard reset (origin always wins)

This agent is a *consumer*, not a long-lived feature branch. Matching origin
is always correct so new pending jobs can land.
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

POLL = int(os.getenv("ETHER_HOST_AGENT_POLL", "1"))
PENDING = ROOT / "artifacts" / "jobs" / "pending"
DONE = ROOT / "artifacts" / "jobs" / "done"
FAILED = ROOT / "artifacts" / "jobs" / "failed"
LOG = ROOT / "memory" / "host_agent" / "agent.log"
STATUS = ROOT / "memory" / "host_agent" / "status.json"

_last_recover_log = 0.0


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
    if cmd and isinstance(cmd[0], str):
        c0 = cmd[0].replace("\\", "/")
        name = Path(c0).name.lower()
        if name in ("python.exe", "python"):
            cand = (ROOT / cmd[0]).resolve() if not Path(cmd[0]).is_absolute() else Path(cmd[0])
            venv_py = ROOT / ".venv" / "Scripts" / "python.exe"
            if cand.is_file():
                cmd = [str(cand)] + list(cmd[1:])
            elif venv_py.is_file():
                cmd = [str(venv_py)] + list(cmd[1:])
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


def git_reset_to_origin(reason: str) -> bool:
    global _last_recover_log
    now = time.time()
    if now - _last_recover_log > 30:
        log(f"git recover ({reason}): reset --hard origin/main")
        _last_recover_log = now
    run(["git", "fetch", "origin"], timeout=120)
    r = run(["git", "reset", "--hard", "origin/main"], timeout=60)
    if r.returncode != 0:
        log(f"reset failed rc={r.returncode} {(r.stderr or '')[:300]}")
        return False
    return True


def git_sync() -> None:
    """Always end aligned with origin/main."""
    run(["git", "fetch", "origin"], timeout=120)
    r = run(["git", "merge", "--ff-only", "origin/main"], timeout=60)
    if r.returncode == 0:
        return
    git_reset_to_origin("ff-only failed / diverged")


def git_push_report(job_id: str, ok: bool, finished_rel: Optional[str] = None) -> None:
    """Best-effort report push. Never leave repo diverged afterward.

    Stage the jobs *directories* (not every individual file).
    This correctly records both the new file in done/failed AND the
    deletion of the pending file, without exploding the command line
    (which previously caused WinError 206).
    """
    paths: List[str] = [
        "artifacts/host_agent_last_job.json",
        "memory/host_agent/status.json",
        "artifacts/jobs/pending",
        "artifacts/jobs/done",
        "artifacts/jobs/failed",
    ]
    for name in ("host_report_latest.md", "host_report_latest.json"):
        p = ROOT / "artifacts" / name
        if p.is_file():
            paths.append(str(p.relative_to(ROOT)))

    run(["git", "add", "-f", "--"] + paths, timeout=90)
    status = "PASS" if ok else "FAIL"
    msg = f"host agent report: job={job_id} {status}"
    c = run(["git", "commit", "-m", msg], timeout=60)
    combined = ((c.stdout or "") + (c.stderr or "")).lower()
    if c.returncode != 0 and "nothing to commit" in combined:
        log("nothing to commit")
        git_sync()
        return
    if c.returncode != 0:
        log(f"commit rc={c.returncode}")
        git_sync()
        return

    p = run(["git", "push", "origin", "main"], timeout=120)
    if p.returncode == 0:
        log("push rc=0")
        return

    log(f"push rc={p.returncode}; rebase retry")
    run(["git", "fetch", "origin"], timeout=120)
    rb = run(["git", "pull", "--rebase", "origin", "main"], timeout=120)
    if rb.returncode == 0:
        p2 = run(["git", "push", "origin", "main"], timeout=120)
        log(f"push retry rc={p2.returncode}")
        if p2.returncode == 0:
            return
    git_reset_to_origin("push could not land")


def list_pending() -> List[Path]:
    PENDING.mkdir(parents=True, exist_ok=True)
    return sorted(
        [p for p in PENDING.glob("*.json") if p.name != ".gitkeep"],
        key=lambda p: p.name,
    )


def run_sprint(name: str) -> int:
    runner = ROOT / "scripts" / "host_runner.ps1"
    if not runner.exists():
        log("host_runner.ps1 missing")
        return 2
    r = run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(runner),
            "-Sprint",
            name,
        ],
        timeout=7200,
    )
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
        "note": job.get("note"),
    }
    (art / "host_agent_last_job.json").write_text(json.dumps(envelope, indent=2), encoding="utf-8")

    dest_dir = DONE if ok else FAILED
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / path.name
    if dest.exists():
        dest = dest_dir / f"{path.stem}_{int(time.time())}.json"
    path.rename(dest)
    finished_rel = str(dest.relative_to(ROOT))
    log(f"JOB END {job_id} ok={ok}")
    write_status(current_job=None, phase="idle", last_job=job_id, last_ok=ok)
    try:
        git_push_report(job_id, ok, finished_rel=finished_rel)
    except Exception as e:
        log(f"push error: {e}")
        git_sync()
    return ok


def main() -> int:
    print("=" * 60, flush=True)
    print("  ETHER host_agent — job queue consumer", flush=True)
    print(f"  root={ROOT}", flush=True)
    print(f"  poll={POLL}s (idle only)", flush=True)
    print("  dashboard: http://127.0.0.1:8787/agent", flush=True)
    print("=" * 60, flush=True)

    git_reset_to_origin("startup")

    PENDING.mkdir(parents=True, exist_ok=True)
    DONE.mkdir(parents=True, exist_ok=True)
    FAILED.mkdir(parents=True, exist_ok=True)

    while True:
        try:
            write_status(current_job=None, phase="polling")
            git_sync()
            jobs = list_pending()
            if not jobs:
                log("idle")
                time.sleep(max(1, POLL))
                continue
            for job_path in jobs:
                process_job(job_path)
                git_sync()
        except KeyboardInterrupt:
            log("stop")
            write_status(phase="stopped")
            return 0
        except Exception as e:
            log(f"loop error: {e}")
            try:
                git_sync()
            except Exception:
                pass
            time.sleep(max(1, POLL))


if __name__ == "__main__":
    raise SystemExit(main())
