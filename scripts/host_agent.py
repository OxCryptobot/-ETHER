#!/usr/bin/env python3
"""ETHER host agent - job queue consumer. Simple and reliable."""
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

POLL = int(os.getenv("ETHER_HOST_AGENT_POLL", "1"))
PENDING = ROOT / "artifacts" / "jobs" / "pending"
DONE = ROOT / "artifacts" / "jobs" / "done"
FAILED = ROOT / "artifacts" / "jobs" / "failed"
STATUS = ROOT / "artifacts" / "host_agent_status.json"
LAST_JOB = ROOT / "artifacts" / "host_agent_last_job.json"
LOG = ROOT / "artifacts" / "host_agent_log.txt"

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
        name = Path(cmd[0].replace("\\", "/")).name.lower()
        if name in ("python.exe", "python"):
            cand = (ROOT / cmd[0]).resolve() if not Path(cmd[0]).is_absolute() else Path(cmd[0])
            venv_py = ROOT / ".venv" / "Scripts" / "python.exe"
            if cand.is_file():
                cmd = [str(cand)] + list(cmd[1:])
            elif venv_py.is_file():
                cmd = [str(venv_py)] + list(cmd[1:])
    return subprocess.run(
        cmd, cwd=str(ROOT), env=os.environ.copy(),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
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
        log(f"reset failed rc={r.returncode}")
        return False
    return True


def git_sync() -> None:
    run(["git", "fetch", "origin"], timeout=120)
    r = run(["git", "merge", "--ff-only", "origin/main"], timeout=60)
    if r.returncode != 0:
        git_reset_to_origin("diverged")


def git_push_report(job_id: str, ok: bool) -> None:
    paths = [
        "artifacts/host_agent_last_job.json",
        "artifacts/host_agent_status.json",
        "artifacts/jobs/pending",
        "artifacts/jobs/done",
        "artifacts/jobs/failed",
    ]
    for p in (ROOT / "artifacts").glob("scoreboard*.json"):
        paths.append(str(p.relative_to(ROOT)))
    for p in (ROOT / "artifacts").glob("trace_*.json"):
        paths.append(str(p.relative_to(ROOT)))
    for name in (
        "strategy_stats.json",
        "preference_summary.json",
        "preferences_tail.jsonl",
    ):
        p = ROOT / "artifacts" / name
        if p.exists():
            paths.append(str(p.relative_to(ROOT)))
    run(["git", "add", "-f", "--"] + paths, timeout=90)
    status = "PASS" if ok else "FAIL"
    c = run(["git", "commit", "-m", f"host agent report: job={job_id} {status}"], timeout=60)
    combined = ((c.stdout or "") + (c.stderr or "")).lower()
    if c.returncode != 0 and "nothing to commit" in combined:
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
    log(f"push rc={p.returncode}; retry")
    run(["git", "fetch", "origin"], timeout=120)
    rb = run(["git", "pull", "--rebase", "origin", "main"], timeout=120)
    if rb.returncode == 0:
        p2 = run(["git", "push", "origin", "main"], timeout=120)
        if p2.returncode == 0:
            log("push retry rc=0")
            return
    git_reset_to_origin("push failed")


def list_pending() -> List[Path]:
    PENDING.mkdir(parents=True, exist_ok=True)
    return sorted([p for p in PENDING.glob("*.json") if p.name != ".gitkeep"], key=lambda p: p.name)


def run_steps(steps: List[Dict[str, Any]], continue_on_fail: bool = False) -> int:
    """Run job steps. Default fail-fast. Measure jobs can set continue_on_fail."""
    last_rc = 0
    for i, step in enumerate(steps, 1):
        argv = step.get("argv")
        cmd = step.get("cmd")
        log(f"step {i}/{len(steps)}: {argv or cmd}")
        if argv:
            r = run([str(x) for x in argv], timeout=int(step.get("timeout", 3600)))
        elif cmd:
            r = run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                    timeout=int(step.get("timeout", 3600)))
        else:
            return 2
        if r.stdout:
            print(r.stdout[-3000:], flush=True)
        if r.stderr:
            print(r.stderr[-1500:], flush=True)
        if r.returncode != 0:
            log(f"step failed rc={r.returncode}")
            last_rc = r.returncode
            step_continue = bool(step.get("continue_on_fail", continue_on_fail))
            if not step_continue:
                return r.returncode
    return last_rc


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
        if job.get("steps"):
            cont = bool(job.get("continue_on_fail", False))
            rc = run_steps(list(job["steps"]), continue_on_fail=cont)
        else:
            log("job has no steps")
            rc = 2
        ok = rc == 0
    except Exception as e:
        log(f"job exception: {e}")
        ok = False

    envelope = {
        "job_id": job_id,
        "ok": ok,
        "rc": rc,
        "finished": datetime.now(timezone.utc).isoformat(),
        "note": job.get("note"),
    }
    LAST_JOB.write_text(json.dumps(envelope, indent=2), encoding="utf-8")

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
        git_sync()
    return ok


def main() -> int:
    print("=" * 60, flush=True)
    print("  ETHER host_agent", flush=True)
    print(f"  root={ROOT}", flush=True)
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
                write_status(current_job=None, phase="idle")
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
