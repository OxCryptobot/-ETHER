"""Disk writer kernel. Self-heal, LIVE attach, evolve, publish."""
from __future__ import annotations
import json, os, subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

def _root() -> Path:
    env = os.environ.get("ETHER_ROOT")
    if env and (Path(env) / "scripts").is_dir():
        return Path(env).resolve()
    win = Path(r"C:\Users\Otcde\ETHER")
    if (win / "scripts").is_dir():
        return win.resolve()
    return Path(__file__).resolve().parents[1]

def _git() -> str:
    for p in (r"C:\Program Files\Git\cmd\git.exe", r"C:\Program Files (x86)\Git\cmd\git.exe"):
        if Path(p).is_file():
            return p
    return "git"

def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
        except Exception:
            return False
        return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False

def _e(exc: BaseException) -> str:
    """Name + message (batch 5): a bare type name hid the deleted heartbeat_plan for 12 days."""
    return f"{type(exc).__name__}: {str(exc)[:160]}"


def _selfcheck(root: Path, row: Dict[str, Any]) -> None:
    """Batch 5: every lazy import on the writer path resolves, or host_main.json says which does not."""
    try:
        from scripts.host_selfcheck import check_imports
        chk = check_imports(root)
    except Exception as exc:
        chk = {"ok": False, "broken": [f"scripts.host_selfcheck: {_e(exc)}"], "n_broken": 1}
    try:  # non-fatal tool check: without ruff the lint goal source stays empty on the host
        from core.agent.goal_source import ruff_bin
        chk["ruff"] = bool(ruff_bin())
    except Exception:
        chk["ruff"] = False
    try:  # batch 10: which OS jail the honest gate gets on this machine (probe runs a trivial child once)
        from core.agent.gate_jail import probe

        pj = probe()
        chk["gate_jail"] = {"mode": pj.get("mode"), "backend": pj.get("backend") or "none",
                            "net": next((t.get("net") for t in pj.get("tried") or [] if t.get("ok")), "")}
    except Exception as exc:
        chk["gate_jail"] = {"error": _e(exc)}
    row["selfcheck"] = chk
    if not chk.get("ok"):
        row["health"] = "degraded"
        row["selfcheck_error"] = "; ".join(chk.get("broken") or [])[:600]
        try:
            art = root / "artifacts"
            art.mkdir(parents=True, exist_ok=True)
            (art / "host_main.json").write_text(json.dumps(row, indent=2, default=str) + "\n", encoding="utf-8")
        except Exception:
            pass


def _pull(root: Path) -> None:
    if os.name != "nt":
        return
    try:
        from scripts.host_pin import pinned
        if pinned(root):
            return  # rolled back locally: do not rebase onto the bad commit (host_pin.py)
    except Exception:
        pass
    from scripts.origin_publish import make_runner, sync_writer
    try:
        git, runner, _token = make_runner(root)
        sync_writer(root, git, runner)
    except Exception:
        return

def _ensure_daemon(root: Path) -> Dict[str, Any]:
    if os.environ.get("ETHER_IN_DAEMON") == "1":
        return {"ok": True, "note": "already_inside_daemon"}
    if os.environ.get("ETHER_SUPERVISOR") == "1":
        # ETHER-Host supervisor is the one long-lived loop; no second loop process.
        return {"ok": True, "note": "supervisor_owns_loop"}
    pid_path = root / "memory" / "daemon" / "daemon.pid"
    if pid_path.is_file():
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
            if _pid_alive(pid):
                return {"ok": True, "already": pid}
        except Exception:
            pass
        try:
            pid_path.unlink(missing_ok=True)
        except Exception:
            pass
    pyw = root / ".venv" / "Scripts" / "pythonw.exe"
    py = pyw if pyw.is_file() else Path(root / ".venv" / "Scripts" / "python.exe")
    script = root / "scripts" / "ether_daemon.py"
    if not script.is_file() or not py.is_file():
        return {"ok": False, "error": "no_daemon"}
    env = os.environ.copy()
    env["ETHER_ROOT"] = str(root)
    env["ETHER_DAEMON_DASHBOARD"] = "0"
    env["ETHER_FLYWHEEL_PUSH"] = "0"
    env["PYTHONPATH"] = str(root)
    try:
        from scripts.win_quiet import popen_hidden
        popen_hidden([str(py), str(script)], cwd=str(root), env=env)
        return {"ok": True, "spawned": True, "dash": False}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__}

def _learn(root: Path, row: Dict[str, Any]) -> None:
    """next_goal + one honest SOTA batch. Same queue the runtime uses, so the
    reported next_goal is the goal the batch will actually try."""
    try:
        from core.agent.sota import lost_kept, next_goal as sota_next_goal
        nxt = sota_next_goal(root)
        row["next_goal"] = nxt["id"] if nxt else "none"
        row["lost_kept"] = len(lost_kept(root))
        from core.agent.sota import seed_depth
        row["seed_depth"] = seed_depth(root)
    except Exception as exc:
        row["next_error"] = _e(exc)
    try:
        from core.agent import goal_source
        data = goal_source.load_index(root)
        row["real_queue"] = {"open": len(goal_source.ranked(root)), "done": len(data.get("done") or []),
                             "dropped": len(data.get("dropped") or {}), "scan_ts": data.get("scan_ts")}
        # batch 10 item 0: open goals next_real will not pick, by reason (exhausted, abort_backoff, ...)
        why = goal_source.why_blocked(root)
        row["real_queue"].update({"selectable": why["selectable"], "blocked": why["blocked"],
                                  "abort_reasons": why["abort_reasons"], "secs_per_file": why["secs_per_file"],
                                  "gate_timeout_s": goal_source.gate_timeout(root, 16)})
        if why.get("next_retry"):
            row["real_queue"]["next_retry"] = why["next_retry"]
    except Exception as exc:
        row["real_queue_error"] = _e(exc)
    try:
        from core.agent.sota import run as sota_run
        from scripts.live_edit_tx import _ask

        def _code(prompt: str, n: int = 240, temperature: float = 0.0) -> str:
            # batch 8: temperature only moves off 0 when ETHER_SAMPLE_TEMP is set (core/agent/sampling.py)
            return _ask(prompt, n=n, edit=True, temperature=temperature)

        row["sota"] = sota_run(root, _code)
        try:
            from core.agent.outcome import publish_summary, summary as learn_summary
            row["learning"] = learn_summary(root)
            row["learning_published"] = publish_summary(root)
        except Exception as exc:
            row["learning_error"] = _e(exc)
        from core.agent.env import write as env_write

        row["env"] = env_write(root)
    except Exception as exc:
        row["runtime_error"] = _e(exc)
    row["agent"] = {"ok": True, "note": "runtime owns the edit"}


def tick() -> Dict[str, Any]:
    """One writer pass. Serialised across processes by artifacts/tick.lock.

    The supervisor, the optional autonomy-host runner and the old daemon all call
    this; the OS lock guarantees at most one pass touches git/attach at a time.
    """
    root = _root()
    from scripts.host_lock import HostLock

    lock = HostLock(root / "artifacts" / "tick.lock")
    if not lock.acquire():
        return {"ts": datetime.now(timezone.utc).isoformat(), "root": str(root), "os": os.name,
                "ok": True, "note": "tick_busy"}
    try:
        return _tick(root)
    finally:
        lock.release()


def _tick(root: Path) -> Dict[str, Any]:
    os.environ["ETHER_ROOT"] = str(root)
    row: Dict[str, Any] = {"ts": datetime.now(timezone.utc).isoformat(), "root": str(root), "os": os.name}
    _selfcheck(root, row)
    if os.name == "nt":
        try:
            from scripts.origin_publish import silence_git
            silence_git(root)
        except Exception:
            pass
        try:
            from scripts.ether_app import mark_alive
            row["alive"] = mark_alive()
        except Exception as exc:
            row["alive_error"] = _e(exc)
        try:
            from scripts.origin_publish import publish
            row["publish"] = publish(root, message="1650 host_main")
        except Exception as exc:
            row["publish_error"] = _e(exc)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            _pull(root)
            # No hard reset: sync_writer (in _pull) rebases and never discards a kept
            # edit that has not reached origin yet (lost-kept goals, 2026-11-19).
            row["reset"] = {"skipped": True, "note": "sync_writer_only"}
            row["runner"] = {"ok": True, "note": "already_actions_runner"}
            row["daemon"] = {"ok": True, "note": "skipped_in_actions"}
            try:
                from scripts.self_heal import arm
                row["heal"] = arm()
            except Exception as exc:
                row["heal_error"] = _e(exc)
            row["keepalive"] = {"ok": True, "note": "runner_watch"}
            _learn(root, row)
        else:
            _pull(root)
            try:
                from scripts.self_heal import arm
                row["heal"] = arm()
            except Exception as exc:
                row["heal_error"] = _e(exc)
            try:
                from scripts.start_runner import start_runner
                row["runner"] = start_runner()
            except Exception as exc:
                row["runner_error"] = _e(exc)
            row["daemon"] = _ensure_daemon(root)
            try:
                from scripts.app_keepalive import ensure_keepalive
                row["keepalive"] = ensure_keepalive(root)
            except Exception as exc:
                row["keepalive_error"] = _e(exc)
            try:
                from scripts.live_host import start_ollama, consume, ollama_up
                row["ollama_start"] = start_ollama()
                row["attach"] = consume({"cmd": "attach"})
                row["ollama"] = ollama_up()
            except Exception as exc:
                row["attach_error"] = _e(exc)
            try:
                from core.kernel.plan import heartbeat_plan
                row["plan"] = heartbeat_plan(stale=False, ollama=bool(row.get("ollama")))
            except Exception as exc:
                # Name + message: "ImportError" alone hid a deleted heartbeat_plan for 12 days.
                row["plan_error"] = _e(exc)
            try:
                from scripts.ether_app import mark_alive
                row["alive"] = mark_alive()
            except Exception as exc:
                row["alive_error"] = _e(exc)
            try:
                from scripts.drain_live_fifo import drain as drain_live
                row["live"] = drain_live(max_jobs=1)
            except Exception as exc:
                row["live_error"] = _e(exc)
            _learn(root, row)
        try:
            from core.kernel.day_learn import learn
            row["day_learn"] = learn(root)
        except Exception as exc:
            row["day_learn_error"] = _e(exc)
        try:
            from core.kernel.proactive import act
            row["proactive"] = act(root)
        except Exception as exc:
            row["proactive_error"] = _e(exc)
        if os.environ.get("GITHUB_ACTIONS") != "true":
            try:
                from scripts.runner_service import ensure_service
                row["service"] = ensure_service()
            except Exception as exc:
                row["service_error"] = _e(exc)
        try:  # batch 9 (W19): refresh the Matrix read model on the 1650 (only ever ran off-Windows)
            from scripts.unison import publish_observer
            publish_observer()
            row["unison"] = {"ok": True}
        except Exception as exc:
            row["unison_error"] = _e(exc)
        # Batch 5: write the row before the final publish so origin shows this tick, not the last one.
        _write_row(root, row)
        try:
            from scripts.origin_publish import publish
            row["publish"] = publish(root, message="1650 host_main")
        except Exception as exc:
            row["publish_error"] = _e(exc)
    else:
        try:
            from scripts.ether_evolve import cycle
            row["evolve"] = cycle()
        except Exception as exc:
            row["evolve_error"] = _e(exc)
        row["note"] = "observe_only"
    _write_row(root, row)
    return row


def _worst(root: Path, row: Dict[str, Any]) -> None:
    """Batch 9: host_main.json health = worst signal of this pass (never upgraded past selfcheck)."""
    try:
        from scripts.host_signals import LEVELS, host_signals, worst
        w = worst(host_signals(row, base=root))
    except Exception as exc:
        row["health"] = "degraded"
        row["health_worst"] = f"host_signals: {_e(exc)}"
        return
    have = row.get("health") if row.get("health") in LEVELS else "ok"
    row["health"] = w["health"] if LEVELS[w["health"]] >= LEVELS[have] else have
    row["health_worst"] = w["worst"]
    row["health_signals"] = w["signals"]


def _write_row(root: Path, row: Dict[str, Any]) -> None:
    if "health_signals" not in row:
        _worst(root, row)
    art = root / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    tmp = art / "host_main.json.tmp"
    tmp.write_text(json.dumps(row, indent=2, default=str) + "\n", encoding="utf-8")
    os.replace(tmp, art / "host_main.json")

if __name__ == "__main__":
    print(json.dumps(tick(), default=str))
