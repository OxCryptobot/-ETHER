#!/usr/bin/env python3
"""ETHER host agent - job queue consumer. Standalone + self-refilling.

2026-08-14 permanent fix:
- On empty pending, call scripts.foreman.tick() so the system never idles
  and does not depend on chat/Grok to enqueue work.
- Still drains FIFO, still reports to GitHub, still recovers on diverge.

2026-08-14 FastTrack:
- Timeouts raise as typed failure_type=timeout on last_job envelope so
  playbooks and lessons can match without parsing free text only.

2026-08-15 PERF 10x:
- git_push_report is lightweight (no full done/ tree every job — prevents
  WinError 206 and massive push latency as history grows).
- Strict FAST-first ranking; LIVE jobs always last.
- continue_on_fail measurement jobs use light report path.
- Explicit live-ledger pending killer support.
- Always push performance_benchmark.json + foreman_state.json.

2026-08-15 LIVENESS:
- push_liveness() every ~60s while idle so artifacts/host_agent_status.json
  on origin always reflects real heartbeat. Fixes false "host offline" when
  the process is alive but not finishing jobs.

2026-08-15b:
- push_liveness logs full git stdout/stderr on failure (no more silent push death).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
_last_heavy_push = 0.0
_last_liveness_push = 0.0
HEAVY_PUSH_INTERVAL = 180  # seconds between full tree pushes
LIVENESS_INTERVAL = 55     # seconds between idle heartbeat pushes


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
        log(f"reset failed rc={r.returncode} out={(r.stdout or '')[:200]} err={(r.stderr or '')[:300]}")
        return False
    return True


def git_sync() -> None:
    run(["git", "fetch", "origin"], timeout=120)
    r = run(["git", "merge", "--ff-only", "origin/main"], timeout=60)
    if r.returncode != 0:
        git_reset_to_origin("diverged")


def push_liveness(reason: str = "idle") -> None:
    """Push status + last_job so remote observability always has a fresh heartbeat.

    Called from idle loops every LIVENESS_INTERVAL seconds. Lightweight.
    On any failure, logs full git stdout/stderr so silent push death is impossible.
    """
    global _last_liveness_push
    now = time.time()
    if now - _last_liveness_push < LIVENESS_INTERVAL:
        return
    _last_liveness_push = now
    try:
        # Always refresh status first so the file content is current
        write_status(current_job=None, phase=reason)
        paths = [
            "artifacts/host_agent_status.json",
            "artifacts/host_agent_last_job.json",
        ]
        if LOG.exists():
            paths.append("artifacts/host_agent_log.txt")
        for name in ("pending", "failed"):
            p = ROOT / "artifacts" / "jobs" / name
            if p.exists():
                paths.append(f"artifacts/jobs/{name}")
        add = run(["git", "add", "-f", "--"] + paths, timeout=45)
        if add.returncode != 0:
            log(f"liveness add rc={add.returncode} err={(add.stderr or '')[:400]}")
        c = run(
            ["git", "commit", "-m", f"host agent liveness: {reason}"],
            timeout=30,
        )
        combined = ((c.stdout or "") + (c.stderr or "")).lower()
        if c.returncode != 0 and "nothing to commit" in combined:
            log(f"liveness nothing to commit ({reason})")
            return
        if c.returncode != 0:
            log(f"liveness commit rc={c.returncode} out={(c.stdout or '')[:200]} err={(c.stderr or '')[:400]}")
            return
        p = run(["git", "push", "origin", "main"], timeout=90)
        if p.returncode == 0:
            log(f"liveness push ok ({reason})")
        else:
            log(f"liveness push FAILED rc={p.returncode} out={(p.stdout or '')[:300]} err={(p.stderr or '')[:500]}")
            # one retry after fetch
            run(["git", "fetch", "origin"], timeout=60)
            rb = run(["git", "pull", "--rebase", "origin", "main"], timeout=60)
            if rb.returncode == 0:
                p2 = run(["git", "push", "origin", "main"], timeout=90)
                if p2.returncode == 0:
                    log(f"liveness push retry ok ({reason})")
                else:
                    log(f"liveness push retry FAILED rc={p2.returncode} err={(p2.stderr or '')[:400]}")
            else:
                log(f"liveness rebase failed rc={rb.returncode} err={(rb.stderr or '')[:300]}")
    except Exception as e:
        log(f"liveness push error: {type(e).__name__}: {e}")


def git_push_report(job_id: str, ok: bool, light: bool = False) -> None:
    """Lightweight by default. Full tree only on interval or non-light jobs."""
    global _last_heavy_push
    now = time.time()
    do_heavy = (not light) or (now - _last_heavy_push > HEAVY_PUSH_INTERVAL)

    paths = [
        "artifacts/host_agent_last_job.json",
        "artifacts/host_agent_status.json",
    ]

    for p in (ROOT / "artifacts").glob("scoreboard*.json"):
        paths.append(str(p.relative_to(ROOT)))
    for p in (ROOT / "artifacts").glob("trace_*.json"):
        paths.append(str(p.relative_to(ROOT)))
    for name in (
        "strategy_stats.json",
        "preference_summary.json",
        "preferences_tail.jsonl",
        "whats_next.json",
        "performance_benchmark.json",
        "foreman_state.json",
    ):
        p = ROOT / "artifacts" / name
        if p.exists():
            paths.append(str(p.relative_to(ROOT)))

    if do_heavy:
        paths.extend([
            "artifacts/jobs/pending",
            "artifacts/jobs/failed",
            "memory/host_agent",
        ])
        _last_heavy_push = now

    run(["git", "add", "-f", "--"] + paths, timeout=90)
    status = "PASS" if ok else "FAIL"
    mode = "light" if light and not do_heavy else "full"
    c = run(
        ["git", "commit", "-m", f"host agent report: job={job_id} {status} ({mode})"],
        timeout=60,
    )
    combined = ((c.stdout or "") + (c.stderr or "")).lower()
    if c.returncode != 0 and "nothing to commit" in combined:
        git_sync()
        return
    if c.returncode != 0:
        log(f"commit rc={c.returncode} err={(c.stderr or '')[:300]}")
        git_sync()
        return
    p = run(["git", "push", "origin", "main"], timeout=120)
    if p.returncode == 0:
        log(f"push rc=0 ({mode})")
        return
    log(f"push rc={p.returncode} err={(p.stderr or '')[:400]}; retry")
    run(["git", "fetch", "origin"], timeout=120)
    rb = run(["git", "pull", "--rebase", "origin", "main"], timeout=120)
    if rb.returncode == 0:
        p2 = run(["git", "push", "origin", "main"], timeout=120)
        if p2.returncode == 0:
            log("push retry rc=0")
            return
        log(f"push retry still failed rc={p2.returncode} err={(p2.stderr or '')[:300]}")
    git_reset_to_origin("push failed")


def _sort_pending_fast_first(paths: List[Path]) -> List[Path]:
    """Strict FAST first. LIVE always last."""
    try:
        from core.job_class import job_class, FAST, LIVE
    except Exception:
        return sorted(paths, key=lambda p: p.name)

    def rank(p: Path) -> tuple:
        try:
            job = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return (1, p.name)
        cls = job_class(job)
        order = 0 if cls == FAST else (2 if cls == LIVE else 1)
        note = str(job.get("note") or "").lower()
        jid = str(job.get("id") or "").lower()
        prio = 0
        if "clean" in jid or "archive" in jid or "kill_live" in jid or "clean" in note:
            prio = -1
        return (order, prio, p.name)

    return sorted(paths, key=rank)


def _enrich_failure_from_scoreboard(envelope: Dict[str, Any]) -> None:
    if envelope.get("ok"):
        return
    art = ROOT / "artifacts"
    if not art.exists():
        return
    boards = sorted(art.glob("scoreboard*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for b in boards[:3]:
        try:
            data = json.loads(b.read_text(encoding="utf-8"))
        except Exception:
            continue
        for row in data.get("results") or []:
            deg = " ".join(str(x) for x in (row.get("degraded") or []))
            if "tool_runtime_failed_terminal" in deg or "timeout" in deg.lower():
                envelope.setdefault("failure_type", "timeout")
                envelope["scoreboard"] = b.name
                return
            if row.get("ok") is False and row.get("mode") == "live":
                envelope.setdefault("failure_type", "live_fail")
                envelope["scoreboard"] = b.name
                return


def list_pending() -> List[Path]:
    PENDING.mkdir(parents=True, exist_ok=True)
    paths = [p for p in PENDING.glob("*.json") if p.name != ".gitkeep"]
    return _sort_pending_fast_first(paths)


def run_steps(steps: List[Dict[str, Any]], continue_on_fail: bool = False) -> Tuple[int, Optional[str]]:
    last_rc = 0
    failure_type: Optional[str] = None
    for i, step in enumerate(steps, 1):
        argv = step.get("argv")
        cmd = step.get("cmd")
        log(f"step {i}/{len(steps)}: {argv or cmd}")
        try:
            if argv:
                r = run([str(x) for x in argv], timeout=int(step.get("timeout", 3600)))
            elif cmd:
                r = run(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                    timeout=int(step.get("timeout", 3600)),
                )
            else:
                return 2, "bad_job"
        except subprocess.TimeoutExpired:
            log("step timeout (typed failure_type=timeout)")
            return 124, "timeout"
        if r.stdout:
            print(r.stdout[-3000:], flush=True)
        if r.stderr:
            print(r.stderr[-1500:], flush=True)
        if r.returncode != 0:
            log(f"step failed rc={r.returncode}")
            last_rc = r.returncode
            failure_type = "step_fail"
            step_continue = bool(step.get("continue_on_fail", continue_on_fail))
            if not step_continue:
                return r.returncode, failure_type
    return last_rc, failure_type if last_rc else None


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
    failure_type: Optional[str] = None
    cont = bool(job.get("continue_on_fail", False))
    try:
        if job.get("steps"):
            rc, failure_type = run_steps(list(job["steps"]), continue_on_fail=cont)
        else:
            log("job has no steps")
            rc = 2
            failure_type = "bad_job"
        ok = rc == 0
    except subprocess.TimeoutExpired:
        log("job timeout")
        ok = False
        rc = 124
        failure_type = "timeout"
    except Exception as e:
        log(f"job exception: {e}")
        ok = False
        failure_type = "exception"

    envelope: Dict[str, Any] = {
        "job_id": job_id,
        "ok": ok,
        "rc": rc,
        "finished": datetime.now(timezone.utc).isoformat(),
        "note": job.get("note"),
    }
    if not ok and failure_type:
        envelope["failure_type"] = failure_type
        if failure_type == "timeout":
            envelope["note"] = f"{job.get('note') or ''} [failure_type=timeout]".strip()
    _enrich_failure_from_scoreboard(envelope)
    LAST_JOB.write_text(json.dumps(envelope, indent=2), encoding="utf-8")

    dest_dir = DONE if ok else FAILED
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / path.name
    if dest.exists():
        dest = dest_dir / f"{path.stem}_{int(time.time())}.json"
    path.rename(dest)
    log(f"JOB END {job_id} ok={ok} failure_type={failure_type}")
    write_status(
        current_job=None,
        phase="idle",
        last_job=job_id,
        last_ok=ok,
        last_failure_type=failure_type,
    )
    light = cont or str(job.get("class") or "").lower() == "fast"
    try:
        git_push_report(job_id, ok, light=light)
    except Exception as e:
        log(f"push error: {e}")
        git_sync()
    return ok


def call_foreman_tick() -> None:
    try:
        from scripts.foreman import tick
        result = tick()
        enq = result.get("enqueued")
        pb = result.get("playbook")
        log(f"foreman.tick enqueued={enq} playbook={pb} cursor={result.get('cursor')} live_skip={result.get('live_skip_remaining')}")
        write_status(
            current_job=None,
            phase="foreman_tick",
            last_enqueued=enq,
            foreman_cursor=result.get("cursor"),
            live_skip_remaining=result.get("live_skip_remaining"),
        )
    except Exception as e:
        log(f"foreman.tick failed: {e}")


def main() -> int:
    print("=" * 60, flush=True)
    print("  ETHER host_agent (self-refilling + PERF 10x + liveness)", flush=True)
    print(f"  root={ROOT}", flush=True)
    print("=" * 60, flush=True)

    git_reset_to_origin("startup")
    PENDING.mkdir(parents=True, exist_ok=True)
    DONE.mkdir(parents=True, exist_ok=True)
    FAILED.mkdir(parents=True, exist_ok=True)

    call_foreman_tick()
    push_liveness("startup")

    while True:
        try:
            write_status(current_job=None, phase="polling")
            git_sync()
            jobs = list_pending()
            if not jobs:
                log("idle -> foreman.tick")
                call_foreman_tick()
                jobs = list_pending()
                if not jobs:
                    write_status(current_job=None, phase="idle")
                    push_liveness("idle")
                    time.sleep(max(2, POLL * 2))
                    continue
            for job_path in jobs:
                process_job(job_path)
                git_sync()
                if len(list_pending()) < 5:
                    call_foreman_tick()
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
