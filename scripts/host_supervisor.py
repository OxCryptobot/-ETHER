"""ETHER-Host supervisor: the one long-lived process on the 1650.

    pythonw scripts/host_supervisor.py          # loop (Windows default)
    python  scripts/host_supervisor.py --once   # one writer pass, then exit

One cycle = stop-file check -> git pull --ff-only (disk updates the writer)
-> ensure Ollama -> `python -m scripts.host_main` in a child process with a
timeout. The child is the writer pass (host_main.tick writes app_alive).
The supervisor never fakes app_alive: it only writes artifacts/supervisor.json.

Singleton: OS lock on artifacts/host.lock (gone when the process dies).
Crash/timeout of a pass -> exponential backoff. Supervisor code changed by
the pull -> release lock, start a fresh copy, exit. Stop: artifacts/host.stop
(written by `host.cmd stop`) or SIGTERM/SIGINT.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ROOT_HERE = Path(__file__).resolve().parents[1]
if str(ROOT_HERE) not in sys.path:
    sys.path.insert(0, str(ROOT_HERE))

from scripts.host_lock import HostLock  # noqa: E402

LOCK_NAME = "host.lock"
STOP_NAME = "host.stop"
STATE_NAME = "supervisor.json"
TICK_TIMEOUT_S = int(os.environ.get("ETHER_TICK_TIMEOUT_S", "1800"))
BACKOFF_BASE_S = float(os.environ.get("ETHER_BACKOFF_BASE_S", "15"))
BACKOFF_MAX_S = float(os.environ.get("ETHER_BACKOFF_MAX_S", "900"))
IDLE_S = 60.0
IDLE_MAX_S = float(os.environ.get("ETHER_IDLE_MAX_S", "900"))
SELF_FILES = ("scripts/host_supervisor.py", "scripts/host_lock.py")


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
                return True
            return False
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def root() -> Path:
    from scripts.host_main import _root
    return _root()


def paths(base: Path) -> Dict[str, Path]:
    art = Path(base) / "artifacts"
    return {"lock": art / LOCK_NAME, "stop": art / STOP_NAME, "state": art / STATE_NAME, "art": art}


def tick():
    """One in-process writer pass (kept for callers/tests that import it)."""
    from scripts.host_main import tick as host_tick
    return host_tick()


def backoff_s(failures: int, base: float = BACKOFF_BASE_S, cap: float = BACKOFF_MAX_S) -> float:
    if failures <= 0:
        return 0.0
    return float(min(cap, base * (2 ** (failures - 1))))


def idle_s() -> float:
    try:
        from core.kernel.poll import pending_count, poll_seconds
        return float(poll_seconds(pending_count()))
    except Exception:
        return IDLE_S


def pass_had_work(base: Path) -> Optional[bool]:
    """False when the last writer pass found nothing to do (queue empty, nothing kept)."""
    try:
        row = json.loads((Path(base) / "artifacts" / "host_main.json").read_text(encoding="utf-8"))
    except Exception:
        return None
    sota = row.get("sota") if isinstance(row, dict) else None
    if not isinstance(sota, dict):
        return None
    if int(sota.get("kept_n") or 0) > 0 or sota.get("tried"):
        return True
    return sota.get("note") != "queue empty"


def dry_backoff_s(streak: int, base: float = IDLE_S, cap: float = IDLE_MAX_S) -> float:
    """Empty queue: 60 s, 120 s, 240 s ... capped (no tight loop, no publish churn)."""
    return float(min(cap, base * (2 ** max(0, streak - 1))))


def _quiet_env(base: Path) -> Dict[str, str]:
    env = dict(os.environ)
    env["ETHER_ROOT"] = str(base)
    env["PYTHONPATH"] = str(base)
    env["ETHER_SUPERVISOR"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "Never"
    env["PYTHONIOENCODING"] = "utf-8"
    # A pass started here is the local writer, never the Actions branch.
    for k in ("GITHUB_ACTIONS", "RUNNER_TRACKING_ID"):
        env.pop(k, None)
    return env


def _run_kwargs() -> Dict[str, Any]:
    kw: Dict[str, Any] = {"stdin": subprocess.DEVNULL, "capture_output": True, "text": True}
    if os.name == "nt":
        kw["creationflags"] = 0x08000000
    return kw


def git_head(base: Path) -> str:
    from scripts.host_main import _git
    try:
        p = subprocess.run([_git(), "-C", str(base), "rev-parse", "HEAD"], timeout=30, env=_quiet_env(base), **_run_kwargs())
        return (p.stdout or "").strip() if p.returncode == 0 else ""
    except Exception:
        return ""


STALE_GIT_LOCK_S = 600


def clear_stale_git_lock(base: Path, now: Optional[float] = None) -> bool:
    """Self-repair: a killed git leaves .git/index.lock and every later git call fails."""
    lock = Path(base) / ".git" / "index.lock"
    try:
        age = (now or time.time()) - lock.stat().st_mtime
    except OSError:
        return False
    if age < STALE_GIT_LOCK_S:
        return False
    try:
        lock.unlink()
        return True
    except OSError:
        return False


def git_pull(base: Path) -> Dict[str, Any]:
    """Fast-forward only. A diverged tree is left for host_main's publish sync."""
    from scripts.host_main import _git
    if not (Path(base) / ".git").exists():
        return {"ok": False, "note": "no_git"}
    cleared = clear_stale_git_lock(base)
    before = git_head(base)
    try:
        p = subprocess.run(
            [_git(), "-C", str(base), "pull", "--ff-only", "--quiet", "origin", "main"],
            timeout=120, env=_quiet_env(base), **_run_kwargs(),
        )
        rc = p.returncode
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "before": before}
    after = git_head(base)
    return {"ok": rc == 0, "rc": rc, "before": before, "after": after,
            "moved": bool(before and after and before != after), "cleared_index_lock": cleared}


def self_changed(base: Path, before: str, after: str) -> bool:
    from scripts.host_main import _git
    if not before or not after or before == after:
        return False
    try:
        p = subprocess.run([_git(), "-C", str(base), "diff", "--name-only", before, after, "--", *SELF_FILES],
                           timeout=30, env=_quiet_env(base), **_run_kwargs())
        return bool((p.stdout or "").strip())
    except Exception:
        return False


def venv_python(base: Path, windowless: bool = False) -> str:
    scripts = Path(base) / ".venv" / ("Scripts" if os.name == "nt" else "bin")
    names = (["pythonw.exe", "python.exe"] if windowless else ["python.exe", "pythonw.exe"]) if os.name == "nt" else ["python"]
    for n in names:
        if (scripts / n).is_file():
            return str(scripts / n)
    return sys.executable


def run_pass(base: Path, timeout: int = TICK_TIMEOUT_S) -> Dict[str, Any]:
    """One writer pass in a child process: fresh code from disk, crash- and hang-isolated."""
    argv = [venv_python(base), "-m", "scripts.host_main"]
    t0 = time.monotonic()
    try:
        p = subprocess.run(argv, cwd=str(base), timeout=timeout, env=_quiet_env(base), **_run_kwargs())
        rc = p.returncode
        tail = (p.stderr or "")[-400:]
    except subprocess.TimeoutExpired:
        rc, tail = -9, "timeout"
    except Exception as exc:
        rc, tail = -1, type(exc).__name__
    return {"rc": rc, "ok": rc == 0, "secs": round(time.monotonic() - t0, 1), "err_tail": tail if rc else ""}


def ensure_ollama() -> Dict[str, Any]:
    """Start `ollama serve` from the long-lived supervisor so it outlives each pass."""
    if os.name != "nt" and os.environ.get("ETHER_SUPERVISOR_OLLAMA") != "1":
        return {"ok": True, "note": "observe_only"}
    # 1650 has 4 GB VRAM: one resident model, one request at a time.
    os.environ.setdefault("OLLAMA_MAX_LOADED_MODELS", "1")
    os.environ.setdefault("OLLAMA_NUM_PARALLEL", "1")
    try:
        from scripts.live_host import start_ollama
        return {"ok": bool(start_ollama())}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__}


def respawn(base: Path) -> Dict[str, Any]:
    argv = [venv_python(base, windowless=True), str(Path(base) / "scripts" / "host_supervisor.py")]
    try:
        from scripts.win_quiet import popen_hidden
        popen_hidden(argv, cwd=str(base), env=_quiet_env(base))
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__}


class Supervisor:
    """Loop with injectable seams so Linux tests can drive it without Windows or git."""

    def __init__(
        self,
        base: Path,
        *,
        pull: Optional[Callable[[Path], Dict[str, Any]]] = None,
        run: Optional[Callable[[Path], Dict[str, Any]]] = None,
        ollama: Optional[Callable[[], Dict[str, Any]]] = None,
        changed: Optional[Callable[[Path, str, str], bool]] = None,
        relaunch: Optional[Callable[[Path], Dict[str, Any]]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        idle: Optional[Callable[[], float]] = None,
        max_cycles: Optional[int] = None,
        work: Optional[Callable[[Path], Optional[bool]]] = None,
    ) -> None:
        self.base = Path(base)
        self.p = paths(self.base)
        self.lock = HostLock(self.p["lock"])
        self.pull = pull or git_pull
        self.run = run or run_pass
        self.ollama = ollama or ensure_ollama
        self.changed = changed or self_changed
        self.relaunch = relaunch or respawn
        self._sleep = sleep or time.sleep
        self.idle = idle or idle_s
        self.max_cycles = max_cycles
        self.work = work or pass_had_work
        self.dry = 0
        self.failures = 0
        self.cycle = 0
        self.stopping = False
        self.history: List[Dict[str, Any]] = []
        self.started = datetime.now(timezone.utc).isoformat()

    def stop_requested(self) -> bool:
        return self.stopping or self.p["stop"].is_file()

    def write_state(self, state: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        row: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "state": state,
            "pid": os.getpid(),
            "started": self.started,
            "cycle": self.cycle,
            "failures": self.failures,
            "note": "supervisor heartbeat only; LIVE is judged from app_alive.json",
        }
        if extra:
            row.update(extra)
        self.p["art"].mkdir(parents=True, exist_ok=True)
        tmp = self.p["state"].with_suffix(".tmp")
        tmp.write_text(json.dumps(row, indent=2, default=str) + "\n", encoding="utf-8")
        os.replace(tmp, self.p["state"])
        return row

    def nap(self, secs: float) -> None:
        """Sleep in 1s slices so a stop file is honoured quickly."""
        end = time.monotonic() + max(0.0, secs)
        while not self.stop_requested():
            left = end - time.monotonic()
            if left <= 0:
                return
            self._sleep(min(1.0, left))

    def once(self) -> Dict[str, Any]:
        self.cycle += 1
        pull = self.pull(self.base)
        if pull.get("moved") and self.changed(self.base, str(pull.get("before") or ""), str(pull.get("after") or "")):
            return {"cycle": self.cycle, "pull": pull, "reload": True}
        oll = self.ollama()
        res = self.run(self.base)
        self.failures = 0 if res.get("ok") else self.failures + 1
        row = {"cycle": self.cycle, "pull": pull, "ollama": oll, "pass": res}
        self.history.append(row)
        return row

    def loop(self) -> int:
        if not self.lock.acquire():
            return 3  # another supervisor owns the writer
        try:
            if self.p["stop"].is_file():
                # `host.cmd stop` is sticky: the 5-min ensure trigger must not undo it.
                self.write_state("stopped", {"reason": "stop_file"})
                return 0
            self.write_state("running")
            while not self.stop_requested():
                row = self.once()
                if row.get("reload"):
                    self.write_state("reloading", {"last": row})
                    self.lock.release()
                    self.relaunch(self.base)
                    return 0
                if self.failures:
                    wait = backoff_s(self.failures)
                else:
                    had = self.work(self.base)
                    self.dry = self.dry + 1 if had is False else 0
                    wait = dry_backoff_s(self.dry) if self.dry else self.idle()
                self.write_state("backoff" if self.failures else ("idle" if self.dry else "running"),
                                 {"last": row, "next_in_s": wait, "dry_streak": self.dry})
                if self.max_cycles is not None and self.cycle >= self.max_cycles:
                    break
                self.nap(wait)
            self.write_state("stopped")
            return 0
        finally:
            self.lock.release()


def _install_signals(sup: Supervisor) -> None:
    def _h(_sig: int, _frm: object) -> None:
        sup.stopping = True
    for name in ("SIGTERM", "SIGINT", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is not None:
            try:
                signal.signal(sig, _h)
            except (ValueError, OSError):
                pass


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    base = root()
    os.environ["ETHER_ROOT"] = str(base)
    if "--once" in args:
        print(json.dumps(tick(), default=str))
        return 0
    if os.name != "nt" and "--loop" not in args:
        # Off the 1650 the writer is observe-only: one pass, no loop.
        print(json.dumps(tick(), default=str))
        return 0
    sup = Supervisor(base)
    _install_signals(sup)
    rc = sup.loop()
    if rc == 3:
        print(json.dumps({"ok": True, "note": "keepalive_already"}))
        return 0
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
