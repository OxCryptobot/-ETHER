#!/usr/bin/env python3
"""ETHER host agent — critical ops: schedule rank + latency budget + measure survive."""
from __future__ import annotations

import json
import os
import shutil
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
ARCH = ROOT / "artifacts" / "jobs" / "failed_archived"
STATUS = ROOT / "artifacts" / "host_agent_status.json"
LAST_JOB = ROOT / "artifacts" / "host_agent_last_job.json"
LOG = ROOT / "artifacts" / "host_agent_log.txt"

_last_recover_log = 0.0
_last_heavy_push = 0.0
_last_liveness_push = 0.0
_last_measure_tick = 0.0
HEAVY_PUSH_INTERVAL = 180
LIVENESS_INTERVAL = 55
MEASURE_INTERVAL = 60


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


def _measure_paths() -> List[str]:
    paths: List[str] = []
    for name in (
        "honest_live_rates.json",
        "phase3_snapshot.json",
        "soft_launch_status.json",
        "measure_tick.json",
        "honest_kpi.json",
        "lora_dry_tick.json",
        "foreman_state.json",
        "playbook_limiter.json",
    ):
        p = ROOT / "artifacts" / name
        if p.exists():
            paths.append(str(p.relative_to(ROOT)))
    return paths


def _light_paths() -> List[str]:
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
    for name in (
        "strategy_stats.json",
        "preference_summary.json",
        "preferences_tail.jsonl",
        "whats_next.json",
        "performance_benchmark.json",
        "foreman_state.json",
        "honest_live_rates.json",
        "phase3_snapshot.json",
        "lora_dry_tick.json",
        "lora_train_last.json",
        "soft_launch_status.json",
        "measure_tick.json",
        "honest_kpi.json",
    ):
        p = ROOT / "artifacts" / name
        if p.exists():
            paths.append(str(p.relative_to(ROOT)))
    critiques = ROOT / "artifacts" / "critiques"
    if critiques.exists():
        paths.append("artifacts/critiques")
    return paths


def _commit_and_push(paths: List[str], message: str, label: str) -> bool:
    if not paths:
        return True
    run(["git", "add", "-f", "--"] + paths, timeout=45)
    c = run(["git", "commit", "-m", message], timeout=30)
    combined = ((c.stdout or "") + (c.stderr or "")).lower()
    if c.returncode != 0 and "nothing to commit" in combined:
        log(f"{label} nothing to commit")
        return True
    if c.returncode != 0:
        log(f"{label} commit rc={c.returncode} err={(c.stderr or '')[:300]}")
        return False
    p = run(["git", "push", "origin", "main"], timeout=90)
    if p.returncode == 0:
        log(f"{label} push ok")
        return True
    log(f"{label} push REJECTED rc={p.returncode} err={(p.stderr or '')[:400]}")
    run(["git", "fetch", "origin"], timeout=120)
    run(["git", "pull", "--rebase", "origin", "main"], timeout=90)
    run(["git", "add", "-f", "--"] + paths, timeout=45)
    run(["git", "commit", "-m", message], timeout=30)
    p2 = run(["git", "push", "origin", "main"], timeout=90)
    if p2.returncode == 0:
        log(f"{label} push ok after rebase")
        return True
    log(f"{label} push STILL FAILED rc={p2.returncode}")
    return False


def purge_live_pending() -> int:
    PENDING.mkdir(parents=True, exist_ok=True)
    ARCH.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%H%M%S")
    killed = 0
    for pat in ("ss_pipeline_ledger_*.json", "*live*ledger*.json"):
        for p in list(PENDING.glob(pat)):
            if p.name == ".gitkeep":
                continue
            dst = ARCH / f"{p.stem}_killed_{stamp}.json"
            try:
                shutil.move(str(p), str(dst))
                killed += 1
            except OSError:
                pass
    if killed:
        log(f"purge_live_pending killed={killed}")
    return killed


def rehydrate_measure() -> None:
    try:
        from core.measure_tick import run as measure_run

        report = measure_run()
        log(f"rehydrate_measure ok={report.get('ok')}")
    except Exception as e:
        log(f"rehydrate_measure error: {type(e).__name__}: {e}")


def git_clean_slate(reason: str) -> bool:
    global _last_recover_log
    now = time.time()
    if now - _last_recover_log > 15:
        log(f"git clean_slate ({reason})")
        _last_recover_log = now
    run(["git", "rebase", "--abort"], timeout=30)
    run(["git", "merge", "--abort"], timeout=30)
    run(["git", "reset", "--mixed", "HEAD"], timeout=30)
    run(["git", "fetch", "origin"], timeout=120)
    r = run(["git", "reset", "--hard", "origin/main"], timeout=60)
    if r.returncode != 0:
        log(f"clean_slate reset failed rc={r.returncode} err={(r.stderr or '')[:300]}")
        return False
    rehydrate_measure()
    return True


def git_reset_to_origin(reason: str) -> bool:
    return git_clean_slate(reason)


def git_sync() -> None:
    run(["git", "fetch", "origin"], timeout=120)
    r = run(["git", "merge", "--ff-only", "origin/main"], timeout=60)
    if r.returncode != 0:
        git_clean_slate("diverged")


def push_liveness(reason: str = "idle") -> None:
    global _last_liveness_push
    now = time.time()
    if now - _last_liveness_push < LIVENESS_INTERVAL:
        return
    _last_liveness_push = now
    try:
        write_status(current_job=None, phase=reason)
        _commit_and_push(_light_paths(), f"host agent liveness: {reason}", f"liveness({reason})")
    except Exception as e:
        log(f"liveness error: {type(e).__name__}: {e}")


def maybe_measure_tick(force: bool = False) -> None:
    global _last_measure_tick
    now = time.time()
    if not force and now - _last_measure_tick < MEASURE_INTERVAL:
        return
    _last_measure_tick = now
    try:
        from core.measure_tick import run as measure_run

        report = measure_run()
        kpi = (report.get("steps") or {}).get("honest_kpi") or {}
        log(
            f"measure_tick ok={report.get('ok')} "
            f"kpi={kpi.get('primary_kpi')} "
            f"live_n={(report.get('steps') or {}).get('honest_live', {}).get('live_n')}"
        )
        paths = _measure_paths()
        if paths:
            _commit_and_push(paths, "host measure_tick: rates+kpi+soft_launch", "measure")
    except Exception as e:
        log(f"measure_tick error: {type(e).__name__}: {e}")


def git_push_report(job_id: str, ok: bool, light: bool = False) -> None:
    global _last_heavy_push
    now = time.time()
    do_heavy = (not light) or (now - _last_heavy_push > HEAVY_PUSH_INTERVAL)
    paths = list(_light_paths())
    for p in (ROOT / "artifacts").glob("scoreboard*.json"):
        paths.append(str(p.relative_to(ROOT)))
    for p in (ROOT / "artifacts").glob("trace_*.json"):
        paths.append(str(p.relative_to(ROOT)))
    if do_heavy:
        paths.extend(["artifacts/jobs/pending", "artifacts/jobs/failed"])
        _last_heavy_push = now
    status = "PASS" if ok else "FAIL"
    mode = "light" if light and not do_heavy else "full"
    msg = f"host agent report: job={job_id} {status} ({mode})"
    try:
        _commit_and_push(paths, msg, f"report({job_id})")
    except Exception as e:
        log(f"report push error: {e}")
        git_clean_slate("report_error")


def _sort_pending_fast_first(paths: List[Path]) -> List[Path]:
    """Critical fix #8: MEASURE > RECOVERY > FAST > LIVE."""
    try:
        from core.job_class import schedule_rank
    except Exception:
        return sorted(paths, key=lambda p: p.name)

    def rank(p: Path) -> tuple:
        try:
            job = json.loads(p.read_text(encoding="utf-8"))
            return schedule_rank(job)
        except Exception:
            return (9, p.name)

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


def _mandatory_critique(envelope: Dict[str, Any]) -> None:
    if envelope.get("ok"):
        return
    try:
        from core.critique_on_fail import critique_fail

        art = critique_fail(
            job_id=str(envelope.get("job_id") or "unknown"),
            failure_type=str(envelope.get("failure_type") or ""),
            note=str(envelope.get("note") or ""),
            enqueue=True,
        )
        if art.get("skipped"):
            log(f"critique skipped: {art.get('reason')}")
        elif art.get("enqueue_skipped"):
            log(f"critique rate-limited: {art.get('enqueue_skipped')}")
        else:
            log(
                f"Labradorite critique id={art.get('id')} hyp={str(art.get('next_hypothesis') or '')[:80]} "
                f"enqueued={art.get('enqueued')}"
            )
    except Exception as e:
        log(f"critique_on_fail error: {type(e).__name__}: {e}")


def list_pending() -> List[Path]:
    PENDING.mkdir(parents=True, exist_ok=True)
    paths = [p for p in PENDING.glob("*.json") if p.name != ".gitkeep"]
    return _sort_pending_fast_first(paths)


def run_steps(
    steps: List[Dict[str, Any]],
    continue_on_fail: bool = False,
    job: Optional[Dict[str, Any]] = None,
) -> Tuple[int, Optional[str]]:
    last_rc = 0
    failure_type: Optional[str] = None
    # Critical fix #4: clamp timeout by latency budget
    budget_cap = 3600
    if job is not None:
        try:
            from core.latency_budget import step_timeout_for_job

            budget_cap = step_timeout_for_job(job, default=3600)
        except Exception:
            pass
    for i, step in enumerate(steps, 1):
        argv = step.get("argv")
        cmd = step.get("cmd")
        raw_to = int(step.get("timeout", 3600))
        to = min(raw_to, budget_cap)
        log(f"step {i}/{len(steps)} timeout={to}s: {argv or cmd}")
        try:
            if argv:
                r = run([str(x) for x in argv], timeout=to)
            elif cmd:
                r = run(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                    timeout=to,
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
            rc, failure_type = run_steps(list(job["steps"]), continue_on_fail=cont, job=job)
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

    if not ok:
        _mandatory_critique(envelope)

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
    light = cont or str(job.get("class") or "").lower() in ("fast", "measure", "recovery")
    try:
        git_push_report(job_id, ok, light=light)
    except Exception as e:
        log(f"push error: {e}")
        git_clean_slate("push_error")
    return ok


def call_foreman_tick() -> None:
    try:
        from scripts.foreman import tick

        result = tick()
        enq = result.get("enqueued")
        pb = result.get("playbook")
        gov = result.get("governor") or {}
        log(
            f"foreman.tick enqueued={enq} playbook={pb} cursor={result.get('cursor')} "
            f"pending={gov.get('pending')} may_steady={gov.get('may_enqueue_steady')}"
        )
        write_status(
            current_job=None,
            phase="foreman_tick",
            last_enqueued=enq,
            foreman_cursor=result.get("cursor"),
            live_skip_remaining=result.get("live_skip_remaining"),
            governor=gov,
        )
    except Exception as e:
        log(f"foreman.tick failed: {e}")


def main() -> int:
    print("=" * 60, flush=True)
    print("  ETHER host_agent (critical ops: governor + latency + kpi)", flush=True)
    print(f"  root={ROOT}", flush=True)
    print("=" * 60, flush=True)

    git_clean_slate("startup")
    PENDING.mkdir(parents=True, exist_ok=True)
    DONE.mkdir(parents=True, exist_ok=True)
    FAILED.mkdir(parents=True, exist_ok=True)

    purge_live_pending()
    call_foreman_tick()
    maybe_measure_tick(force=True)
    push_liveness("startup")

    while True:
        try:
            write_status(current_job=None, phase="polling")
            git_sync()
            purge_live_pending()
            jobs = list_pending()
            if not jobs:
                log("idle -> foreman.tick + measure_tick")
                call_foreman_tick()
                maybe_measure_tick()
                jobs = list_pending()
                if not jobs:
                    write_status(current_job=None, phase="idle")
                    push_liveness("idle")
                    time.sleep(max(2, POLL * 2))
                    continue
            for job_path in jobs:
                process_job(job_path)
                git_sync()
                if len(list_pending()) < 3:
                    call_foreman_tick()
                    maybe_measure_tick()
        except KeyboardInterrupt:
            log("stop")
            write_status(phase="stopped")
            return 0
        except Exception as e:
            log(f"loop error: {e}")
            try:
                git_clean_slate("loop_error")
            except Exception:
                pass
            time.sleep(max(1, POLL))


if __name__ == "__main__":
    raise SystemExit(main())
