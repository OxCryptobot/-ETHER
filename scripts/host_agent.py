#!/usr/bin/env python3
"""ETHER host agent — moonshots + chat bus push for Grok bridge.

2026-08-22d: when chat_bridge marks dirty, include artifacts/chat/ on liveness push
so Grok sees outbox escalations on origin within ~55s.
"""
from __future__ import annotations

import importlib
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
LOG_MAX_BYTES = int(os.getenv("ETHER_HOST_LOG_MAX_BYTES", str(8 * 1024 * 1024)))

_last_recover_log = 0.0
_last_heavy_push = 0.0
_last_liveness_push = 0.0
_last_measure_tick = 0.0
_last_rate_climb = 0.0
_last_gpu_sample = 0.0
_last_chat_push = 0.0
HEAVY_PUSH_INTERVAL = 180
LIVENESS_INTERVAL = 55
CHAT_PUSH_INTERVAL = 12  # fast path when bus dirty
MEASURE_INTERVAL = 60
RATE_CLIMB_INTERVAL = 90
GPU_SAMPLE_INTERVAL = 15
_gpu_cache: Dict[str, Any] = {}


def _rotate_log_if_needed() -> None:
    try:
        if LOG.exists() and LOG.stat().st_size > LOG_MAX_BYTES:
            bak = LOG.with_suffix(".txt.prev")
            if bak.exists():
                bak.unlink()
            LOG.rename(bak)
    except Exception:
        try:
            LOG.write_text("", encoding="utf-8")
        except Exception:
            pass


def log(msg: str) -> None:
    line = f"[{datetime.now(timezone.utc).isoformat()}] {msg}"
    print(line, flush=True)
    try:
        _rotate_log_if_needed()
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _gpu_snapshot(force: bool = False) -> Dict[str, Any]:
    global _last_gpu_sample, _gpu_cache
    now = time.time()
    if not force and _gpu_cache and (now - _last_gpu_sample) < GPU_SAMPLE_INTERVAL:
        return _gpu_cache
    try:
        from core.gpu_metrics import snapshot_for_status

        _gpu_cache = snapshot_for_status()
        _last_gpu_sample = now
    except Exception as e:
        _gpu_cache = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        _last_gpu_sample = now
    return _gpu_cache


def write_status(**extra: Any) -> None:
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    gpu = _gpu_snapshot()
    payload = {
        "heartbeat": datetime.now(timezone.utc).isoformat(),
        "poll_s": POLL,
        "root": str(ROOT),
        "gpu": gpu,
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
        cmd,
        cwd=str(ROOT),
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
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
        "latency_slo.json",
        "live_budget.json",
        "honest_sparkline.json",
        "context_budget.json",
        "scoreboard_latest.json",
        "shadow_tags.json",
        "gem_energy.json",
        "ast_edit_kpi.json",
        "smoothness.json",
        "microbench.json",
        "lora_dry_tick.json",
        "foreman_state.json",
        "playbook_limiter.json",
        "timeout_diagnosis.json",
        "live_fixture_policy.json",
        "timeout_retirement.json",
        "push_hygiene.json",
        "eligible_rates.json",
        "host_health.json",
        "phase1_gate.json",
        "honest_path_progress.json",
        "pipeline_strangler.json",
        "phase1d_status.json",
        "gpu_metrics.json",
    ):
        p = ROOT / "artifacts" / name
        if p.exists():
            paths.append(str(p.relative_to(ROOT)))
    return paths


def _chat_paths() -> List[str]:
    try:
        from core.chat_bridge import chat_paths_for_push

        return chat_paths_for_push()
    except Exception:
        paths: List[str] = []
        chat = ROOT / "artifacts" / "chat"
        if chat.exists():
            for sub in ("inbox", "outbox", "turns", "archive"):
                if (chat / sub).exists():
                    paths.append(f"artifacts/chat/{sub}")
            if (chat / "pending_grok.json").exists():
                paths.append("artifacts/chat/pending_grok.json")
        if (ROOT / "artifacts" / "chat_turn_latest.json").exists():
            paths.append("artifacts/chat_turn_latest.json")
        return paths


def _light_paths() -> List[str]:
    paths = [
        "artifacts/host_agent_status.json",
        "artifacts/host_agent_last_job.json",
    ]
    for name in ("pending", "failed"):
        p = ROOT / "artifacts" / "jobs" / name
        if p.exists():
            paths.append(f"artifacts/jobs/{name}")
    paths.extend(_measure_paths())
    paths.extend(_chat_paths())
    for name in (
        "strategy_stats.json",
        "preference_summary.json",
        "preferences_tail.jsonl",
        "whats_next.json",
        "performance_benchmark.json",
        "gpu_metrics.json",
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
    paths = [p for p in paths if not p.replace("\\", "/").endswith("host_agent_log.txt")]
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
        try:
            from core.chat_bridge import clear_dirty

            clear_dirty()
        except Exception:
            pass
        return True
    err = ((p.stderr or "") + (p.stdout or ""))[:500]
    log(f"{label} push REJECTED rc={p.returncode} err={err}")
    run(["git", "fetch", "origin"], timeout=120)
    run(["git", "pull", "--rebase", "origin", "main"], timeout=90)
    run(["git", "add", "-f", "--"] + paths, timeout=45)
    run(["git", "commit", "-m", message], timeout=30)
    p2 = run(["git", "push", "origin", "main"], timeout=90)
    if p2.returncode == 0:
        log(f"{label} push ok after rebase")
        try:
            from core.chat_bridge import clear_dirty

            clear_dirty()
        except Exception:
            pass
        return True
    err2 = ((p2.stderr or "") + (p2.stdout or ""))[:500]
    log(f"{label} push STILL FAILED rc={p2.returncode} err={err2}")
    return False


def maybe_push_chat_bus() -> None:
    """Fast push when operator escalated to Grok (dirty flag)."""
    global _last_chat_push
    now = time.time()
    if now - _last_chat_push < CHAT_PUSH_INTERVAL:
        return
    try:
        from core.chat_bridge import is_dirty, chat_paths_for_push

        if not is_dirty():
            return
        paths = chat_paths_for_push()
        if not paths:
            return
        _last_chat_push = now
        write_status(current_job=None, phase="chat_push")
        ok = _commit_and_push(paths, "chat bus: outbox/turns for Grok bridge", "chat_bus")
        log(f"chat_bus push ok={ok} paths={len(paths)}")
    except Exception as e:
        log(f"chat_bus push error: {type(e).__name__}: {e}")


def _is_gate_sample(job: Dict[str, Any]) -> bool:
    cls = str(job.get("class") or "").strip().lower()
    note = str(job.get("note") or "").lower()
    jid = str(job.get("id") or "").lower()
    hay = f"{cls} {note} {jid}"
    return (
        cls == "gate_sample"
        or "gate_sample" in hay
        or "eligible_live" in hay
        or "controlled live" in hay
        or "controlled_live" in hay
        or jid.startswith("auto_rc_")
    )


def _is_measurement_job(job: Dict[str, Any]) -> bool:
    cls = str(job.get("class") or "").strip().lower()
    if cls in ("gate_sample", "measure", "recovery"):
        return True
    if bool(job.get("continue_on_fail")):
        return True
    return _is_gate_sample(job)


def purge_live_pending() -> int:
    PENDING.mkdir(parents=True, exist_ok=True)
    ARCH.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%H%M%S")
    killed = 0
    for pat in ("ss_pipeline_ledger_*.json", "*live*ledger*.json"):
        for p in list(PENDING.glob(pat)):
            if p.name == ".gitkeep":
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if _is_gate_sample(data):
                    continue
            except Exception:
                pass
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
        log(f"clean_slate reset failed rc={r.returncode}")
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
        _gpu_snapshot(force=True)
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
        sm = (report.get("steps") or {}).get("smoothness") or {}
        log(
            f"measure_tick ok={report.get('ok')} smoothness={sm.get('score')} "
            f"kpi={(report.get('steps') or {}).get('honest_kpi', {}).get('primary_kpi')}"
        )
        paths = _measure_paths()
        if paths:
            _commit_and_push(paths, "host measure_tick: moonshot panels", "measure")
    except Exception as e:
        log(f"measure_tick error: {type(e).__name__}: {e}")


def maybe_auto_rate_climb(force: bool = False) -> None:
    global _last_rate_climb
    now = time.time()
    if not force and now - _last_rate_climb < RATE_CLIMB_INTERVAL:
        return
    pending = [p for p in PENDING.glob("*.json") if p.name != ".gitkeep"]
    if pending:
        return
    try:
        import core.auto_rate_climb as arc

        importlib.reload(arc)

        def _wj(job: Dict[str, Any]):
            PENDING.mkdir(parents=True, exist_ok=True)
            path = PENDING / f"{job['id']}.json"
            job = dict(job)
            job.setdefault("created", datetime.now(timezone.utc).isoformat())
            job.setdefault("source", "host_agent_idle_rate_climb")
            path.write_text(json.dumps(job, indent=2), encoding="utf-8")
            return path

        state: Dict[str, Any] = {}
        jid = arc.maybe_enqueue(state, pending=set(), write_job=_wj)
        if jid:
            _last_rate_climb = now
            log(f"auto_rate_climb enqueued={jid} status={state.get('rate_climb_status')}")
            write_status(
                current_job=None,
                phase="rate_climb",
                last_enqueued=jid,
                rate_climb_status=state.get("rate_climb_status"),
            )
        else:
            log(f"auto_rate_climb skip status={state.get('rate_climb_status')}")
    except Exception as e:
        log(f"auto_rate_climb error: {type(e).__name__}: {e}")


def git_push_report(job_id: str, ok: bool, light: bool = False) -> None:
    global _last_heavy_push
    now = time.time()
    do_heavy = (not light) or (now - _last_heavy_push > HEAVY_PUSH_INTERVAL)
    paths = list(_light_paths())
    for p in (ROOT / "artifacts").glob("scoreboard*.json"):
        paths.append(str(p.relative_to(ROOT)))
    if do_heavy:
        paths.extend(["artifacts/jobs/pending", "artifacts/jobs/failed"])
        _last_heavy_push = now
    status = "PASS" if ok else "FAIL"
    mode = "light" if light and not do_heavy else "full"
    try:
        _commit_and_push(paths, f"host agent report: job={job_id} {status} ({mode})", f"report({job_id})")
    except Exception as e:
        log(f"report push error: {e}")
        git_clean_slate("report_error")


def _sort_pending_fast_first(paths: List[Path]) -> List[Path]:
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

    sorted_paths = sorted(paths, key=rank)
    try:
        from core.host_schedule import filter_fast_first, filter_live_denylist

        sorted_paths = filter_fast_first(sorted_paths)
        sorted_paths = filter_live_denylist(sorted_paths)
        return sorted_paths
    except Exception:
        return sorted_paths


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
            log(f"Labradorite critique id={art.get('id')} enqueued={art.get('enqueued')}")
    except Exception as e:
        log(f"critique_on_fail error: {type(e).__name__}: {e}")
    try:
        from core.zero_click_recovery import maybe_recover

        zid = maybe_recover(envelope)
        if zid:
            log(f"zero_click_recovery enqueued={zid}")
    except Exception as e:
        log(f"zero_click error: {type(e).__name__}: {e}")


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
    budget_cap = 3600
    if job is not None:
        try:
            from core.latency_budget import step_timeout_for_job

            budget_cap = step_timeout_for_job(job, default=3600)
        except Exception:
            pass
        try:
            lb = job.get("live_budget") or {}
            if lb.get("max_wall_s"):
                budget_cap = min(budget_cap, int(lb["max_wall_s"]))
        except Exception:
            pass
    for i, step in enumerate(steps, 1):
        argv = step.get("argv")
        cmd = step.get("cmd")
        to = min(int(step.get("timeout", 3600)), budget_cap)
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
            if not bool(step.get("continue_on_fail", continue_on_fail)):
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

    try:
        from core.live_budget import apply_to_job

        job = apply_to_job(job)
        if job.get("live_budget"):
            log(
                f"live_budget applied max_wall_s={job['live_budget'].get('max_wall_s')} "
                f"class={job['live_budget'].get('budget_class')} job={job_id}"
            )
    except Exception as e:
        log(f"live_budget skip: {type(e).__name__}: {e}")

    try:
        from core.job_class import job_class, LIVE
        from core.queue_governor import training_wheels_on

        if training_wheels_on() and job_class(job) == LIVE:
            if _is_gate_sample(job):
                log(f"GATE_SAMPLE exception: allow LIVE under wheels job={job_id}")
            else:
                log(f"TRAINING_WHEELS: skip LIVE job {job_id}")
                FAILED.mkdir(parents=True, exist_ok=True)
                path.rename(FAILED / f"{path.stem}_wheels_skip.json")
                return False
    except Exception:
        pass

    try:
        from core.job_class import job_class, LIVE
        from core.live_fixture_policy import should_skip_live

        if job_class(job) == LIVE and not _is_gate_sample(job):
            dec = should_skip_live(job=job)
            if dec.get("skip"):
                log(f"LIVE_DENYLIST: skip {job_id} reason={dec.get('reason')}")
                FAILED.mkdir(parents=True, exist_ok=True)
                path.rename(FAILED / f"{path.stem}_deny_skip.json")
                return False
    except Exception:
        pass

    log(f"JOB START {job_id}")
    write_status(current_job=job_id, phase="running")
    ok = False
    rc = 1
    failure_type: Optional[str] = None
    cont = bool(job.get("continue_on_fail", False))
    is_meas = _is_measurement_job(job)
    try:
        if job.get("steps"):
            rc, failure_type = run_steps(list(job["steps"]), continue_on_fail=cont, job=job)
        else:
            rc = 2
            failure_type = "bad_job"
        ok = rc == 0
    except subprocess.TimeoutExpired:
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
        "class": job.get("class"),
        "measurement": is_meas,
    }
    if job.get("live_budget"):
        envelope["live_budget"] = job["live_budget"]
    if not ok and failure_type:
        envelope["failure_type"] = failure_type
        if failure_type == "timeout":
            envelope["note"] = f"{job.get('note') or ''} [failure_type=timeout]".strip()
    _enrich_failure_from_scoreboard(envelope)
    LAST_JOB.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    if not ok:
        _mandatory_critique(envelope)

    if is_meas:
        dest_dir = DONE
        log(f"MEASUREMENT outcome → done/ (ok={ok} failure_type={failure_type})")
    else:
        dest_dir = DONE if ok else FAILED
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / path.name
    if dest.exists():
        dest = dest_dir / f"{path.stem}_{int(time.time())}.json"
    path.rename(dest)
    log(f"JOB END {job_id} ok={ok} failure_type={failure_type} dest={dest_dir.name}")
    write_status(
        current_job=None,
        phase="idle",
        last_job=job_id,
        last_ok=ok,
        last_failure_type=failure_type,
    )
    light = cont or is_meas or str(job.get("class") or "").lower() in (
        "fast",
        "measure",
        "recovery",
        "gate_sample",
    )
    try:
        git_push_report(job_id, ok, light=light)
    except Exception as e:
        log(f"push error: {e}")
        git_clean_slate("push_error")
    return ok


def call_foreman_tick() -> None:
    try:
        import scripts.foreman as foreman_mod

        importlib.reload(foreman_mod)
        result = foreman_mod.tick()
        log(
            f"foreman.tick enqueued={result.get('enqueued')} playbook={result.get('playbook')} "
            f"cursor={result.get('cursor')} rate_climb={result.get('rate_climb_status')}"
        )
        write_status(
            current_job=None,
            phase="foreman_tick",
            last_enqueued=result.get("enqueued"),
            foreman_cursor=result.get("cursor"),
            governor=result.get("governor"),
            rate_climb_status=result.get("rate_climb_status"),
        )
    except Exception as e:
        log(f"foreman.tick failed: {e}")


def main() -> int:
    print(
        "ETHER host_agent (GPU + chat_bus push + reload-foreman + idle auto_rate_climb)",
        flush=True,
    )
    _rotate_log_if_needed()
    git_clean_slate("startup")
    PENDING.mkdir(parents=True, exist_ok=True)
    DONE.mkdir(parents=True, exist_ok=True)
    FAILED.mkdir(parents=True, exist_ok=True)
    purge_live_pending()
    call_foreman_tick()
    maybe_auto_rate_climb(force=True)
    maybe_measure_tick(force=True)
    _gpu_snapshot(force=True)
    push_liveness("startup")
    while True:
        try:
            write_status(current_job=None, phase="polling")
            git_sync()
            maybe_push_chat_bus()
            purge_live_pending()
            jobs = list_pending()
            if not jobs:
                call_foreman_tick()
                maybe_auto_rate_climb()
                maybe_measure_tick()
                maybe_push_chat_bus()
                jobs = list_pending()
                if not jobs:
                    write_status(current_job=None, phase="idle")
                    push_liveness("idle")
                    time.sleep(max(2, POLL * 2))
                    continue
            for job_path in jobs:
                process_job(job_path)
                git_sync()
                maybe_push_chat_bus()
                if len(list_pending()) < 3:
                    call_foreman_tick()
                    maybe_auto_rate_climb()
                    maybe_measure_tick()
        except KeyboardInterrupt:
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
