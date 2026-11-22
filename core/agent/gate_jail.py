"""Batch 10: OS-level jail for honest-gate test runs (audit W4 remainder, "no process jail").

Batch 9 moved the gate's pytest into a synced mirror with a scrubbed environment. The candidate
function still ran as an ordinary child of the writer: no memory / process / CPU cap, network
open, and on Linux the real checkout writable. This module wraps that one subprocess.

ETHER_GATE_JAIL:
  auto (default) -- use the strongest backend that *passes a self-probe on this machine*; if no
                    backend passes, run exactly as batch 9 did (scrubbed env, mirror) and say so in
                    the result (`jail: "none: <why>"`). Never weaker than batch 9.
  1 / on         -- required: if no backend passes the probe the run is refused (rc -7, the gate
                    then aborts the attempt with reward 0).
  0 / off        -- batch 9 behaviour.

Backends (first that probes OK wins):
  linux  bwrap    bubblewrap: whole filesystem read-only except the run's cwd (the mirror) and the
                  temp dir, no network namespace access (--unshare-net), own session,
                  --die-with-parent, + rlimits below. Same uid (no root mapping).
  linux  unshare  `unshare --map-current-user --net`: no network, + rlimits. Filesystem writable.
  posix  rlimit   rlimits only: address space (ETHER_GATE_JAIL_MEM_MB), CPU seconds, file size,
                  no core dumps, own process group (the whole group is killed on timeout).
  win    job      Windows Job Object via ctypes (no pywin32): child created suspended, assigned to
                  the job, then resumed. KILL_ON_JOB_CLOSE (no stray grandchildren survive the
                  run), job memory cap, active-process cap, job CPU-time cap, die on unhandled
                  exception, UI restrictions (no clipboard / desktop switch / ExitWindows /
                  system parameters). On timeout the whole job is terminated.

What this is NOT (honest limits):
  - Not a security boundary against a determined attacker. bwrap/unshare give real kernel
    namespaces, but rlimit-only and the Windows job do not isolate the filesystem or network.
  - Windows: the child still runs with the owner's user token (no restricted / low-integrity
    token: a low-IL child cannot write the mirror without relabelling it; left as future work),
    and a Job Object cannot block network. scripts/gate_firewall.ps1 (admin, never run
    automatically) adds an outbound-block firewall rule for a dedicated gate interpreter
    (ETHER_GATE_PYTHON); see docs/BATCH10.md for why a venv redirector makes that best-effort.
  - The Windows path is unit-tested with mocks on Linux; on the 1650 it is proven only by
    probe() at run time (selfcheck records it in host_main.json as `gate_jail`).
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

MODES = ("auto", "on", "off")
_PROBE: Dict[str, Any] = {}


def mode() -> str:
    raw = os.getenv("ETHER_GATE_JAIL", "auto").strip().lower()
    if raw in ("1", "on", "true", "yes", "required"):
        return "on"
    if raw in ("0", "off", "false", "no"):
        return "off"
    return "auto"


def mem_mb() -> int:
    return max(256, int(os.getenv("ETHER_GATE_JAIL_MEM_MB", "4096")))


def max_procs() -> int:
    return max(4, int(os.getenv("ETHER_GATE_JAIL_PROCS", "64")))


def cpu_s(timeout: Optional[float]) -> int:
    env = os.getenv("ETHER_GATE_JAIL_CPU_S")
    if env:
        return max(5, int(env))
    return int((timeout or 180) * 2 + 30)


def net_off() -> bool:
    return os.getenv("ETHER_GATE_JAIL_NET", "0") != "1"  # 1 = allow network (debug only)


@dataclass
class Result:
    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    jail: str = "off"
    info: Dict[str, Any] = field(default_factory=dict)


# ------------------------------------------------------------------ posix

def _rlimits(mem: int, cpu: int) -> Callable[[], None]:
    def apply() -> None:  # runs in the child between fork and exec
        import resource

        lim = mem * 1024 * 1024
        for name, value in (("RLIMIT_AS", lim), ("RLIMIT_CPU", cpu), ("RLIMIT_CORE", 0),
                            ("RLIMIT_FSIZE", 1024 * 1024 * 1024)):
            res = getattr(resource, name, None)
            if res is None:
                continue
            try:
                _soft, hard = resource.getrlimit(res)
                want = value if hard == resource.RLIM_INFINITY else min(value, hard)
                resource.setrlimit(res, (want, want if name == "RLIMIT_CORE" else hard))
            except (ValueError, OSError):
                continue
    return apply


def _bwrap_prefix(cwd: str, writable: Sequence[str]) -> List[str]:
    bw = shutil.which("bwrap")
    if not bw:
        return []
    argv = [bw, "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc"]
    seen = set()
    for path in [tempfile.gettempdir(), cwd, *writable]:
        real = os.path.realpath(path)
        if real in seen or not os.path.isdir(real):
            continue
        seen.add(real)
        argv += ["--bind", real, real]
    if net_off():
        argv.append("--unshare-net")
    argv += ["--die-with-parent", "--new-session", "--chdir", os.path.realpath(cwd), "--"]
    return argv


def _unshare_prefix() -> List[str]:
    us = shutil.which("unshare")
    if not us or not net_off():
        return []
    return [us, "--map-current-user", "--net", "--"]


def _posix_backends(cwd: str, writable: Sequence[str]) -> List[tuple]:
    out = []
    if sys.platform.startswith("linux"):
        pre = _bwrap_prefix(cwd, writable)
        if pre:
            out.append(("bwrap", pre))
        pre = _unshare_prefix()
        if pre:
            out.append(("unshare", pre))
    out.append(("rlimit", []))
    return out


def _run_posix(prefix: List[str], name: str, argv: Sequence[str], cwd: str, env: Dict[str, str],
               timeout: Optional[float]) -> Result:
    proc = subprocess.Popen([*prefix, *argv], cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, start_new_session=True, preexec_fn=_rlimits(mem_mb(), cpu_s(timeout)))
    try:
        out, err = proc.communicate(timeout=timeout)
        return Result(proc.returncode, out or "", err or "", False, name)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()
        out, err = proc.communicate()
        return Result(-9, out or "", err or "", True, name)


# ------------------------------------------------------------------ windows

CREATE_SUSPENDED = 0x00000004
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000
JOB_OBJECT_LIMIT_PROCESS_TIME = 0x00000002
JOB_OBJECT_LIMIT_JOB_TIME = 0x00000004
JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x00000400
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JobObjectBasicUIRestrictions = 4
JobObjectExtendedLimitInformation = 9
UI_RESTRICT = 0x02 | 0x04 | 0x08 | 0x10 | 0x20 | 0x40 | 0x80  # clipboard r/w, sysparams, display, atoms, desktop, exitwindows
LIMIT_FLAGS = (JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_ACTIVE_PROCESS | JOB_OBJECT_LIMIT_JOB_MEMORY
               | JOB_OBJECT_LIMIT_JOB_TIME | JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION)


def _win_structs() -> Dict[str, Any]:
    import ctypes
    from ctypes import wintypes

    class BASIC(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class IO(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                                                    "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class EXTENDED(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BASIC), ("IoInfo", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    class UI(ctypes.Structure):
        _fields_ = [("UIRestrictionsClass", wintypes.DWORD)]

    return {"BASIC": BASIC, "IO": IO, "EXTENDED": EXTENDED, "UI": UI}


def job_limits(timeout: Optional[float]) -> Dict[str, int]:
    """The numbers the Job Object gets (pure; unit-tested on every OS)."""
    return {
        "flags": LIMIT_FLAGS,
        "job_memory": mem_mb() * 1024 * 1024,
        "active_processes": max_procs(),
        "job_time_100ns": cpu_s(timeout) * 10_000_000,
        "ui": UI_RESTRICT,
    }


def _kernel32() -> Any:
    import ctypes

    return ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]


def _ntdll() -> Any:
    import ctypes

    return ctypes.WinDLL("ntdll")  # type: ignore[attr-defined]


class WinJob:
    """One Job Object. Raises OSError on any failed Win32 call (caller decides fallback)."""

    def __init__(self, timeout: Optional[float], k32: Any = None, structs: Optional[Dict[str, Any]] = None) -> None:
        import ctypes

        self.k32 = k32 if k32 is not None else _kernel32()
        self.s = structs if structs is not None else _win_structs()
        self.handle = self.k32.CreateJobObjectW(None, None)
        if not self.handle:
            raise OSError("CreateJobObjectW failed")
        lim = job_limits(timeout)
        ext = self.s["EXTENDED"]()
        ext.BasicLimitInformation.LimitFlags = lim["flags"]
        ext.BasicLimitInformation.ActiveProcessLimit = lim["active_processes"]
        ext.BasicLimitInformation.PerJobUserTimeLimit = lim["job_time_100ns"]
        ext.JobMemoryLimit = lim["job_memory"]
        if not self.k32.SetInformationJobObject(self.handle, JobObjectExtendedLimitInformation,
                                                ctypes.byref(ext), ctypes.sizeof(ext)):
            self.close()
            raise OSError("SetInformationJobObject(limits) failed")
        ui = self.s["UI"]()
        ui.UIRestrictionsClass = lim["ui"]
        self.ui = bool(self.k32.SetInformationJobObject(self.handle, JobObjectBasicUIRestrictions,
                                                        ctypes.byref(ui), ctypes.sizeof(ui)))
        self.limits = lim

    def assign(self, process_handle: int) -> None:
        if not self.k32.AssignProcessToJobObject(self.handle, process_handle):
            raise OSError("AssignProcessToJobObject failed")

    def terminate(self) -> None:
        if self.handle:
            self.k32.TerminateJobObject(self.handle, 1)

    def close(self) -> None:
        if self.handle:
            self.k32.CloseHandle(self.handle)  # KILL_ON_JOB_CLOSE: every process left in the job dies
            self.handle = None


def _run_windows(argv: Sequence[str], cwd: str, env: Dict[str, str], timeout: Optional[float],
                 job_factory: Callable[..., Any] = WinJob, popen: Callable[..., Any] = subprocess.Popen,
                 resume: Optional[Callable[[Any], int]] = None) -> Result:
    job = job_factory(timeout)
    flags = CREATE_SUSPENDED | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    proc = popen(list(argv), cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                 creationflags=flags)
    try:
        try:
            job.assign(int(proc._handle))
            status = (resume or (lambda p: _ntdll().NtResumeProcess(int(p._handle))))(proc)
            if status:
                raise OSError(f"NtResumeProcess status {status}")
        except Exception:
            proc.kill()
            proc.communicate()
            raise
        try:
            out, err = proc.communicate(timeout=timeout)
            return Result(proc.returncode, out or "", err or "", False, "job", {"limits": job.limits})
        except subprocess.TimeoutExpired:
            job.terminate()
            out, err = proc.communicate()
            return Result(-9, out or "", err or "", True, "job", {"limits": job.limits})
    finally:
        job.close()


# ------------------------------------------------------------------ plain + dispatch

def _run_plain(argv: Sequence[str], cwd: str, env: Dict[str, str], timeout: Optional[float], name: str) -> Result:
    try:
        proc = subprocess.run(list(argv), cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
        return Result(proc.returncode, proc.stdout or "", proc.stderr or "", False, name)
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        return Result(-9, out, "", True, name)


PROBE_CODE = (
    "import os,sys\n"
    "net='n/a'\n"
    "try:\n"
    "    import socket; s=socket.socket(); s.settimeout(1.5)\n"
    "    net='open' if s.connect_ex(('1.1.1.1',53))==0 else 'blocked'\n"
    "except Exception: net='blocked'\n"
    "print('ETHER_JAIL_OK', net)\n"
)


def _probe_one(name: str, prefix: List[str]) -> Dict[str, Any]:
    t0 = time.monotonic()
    cwd = tempfile.mkdtemp(prefix="ether_jail_probe_")
    try:
        env = {k: v for k, v in os.environ.items() if k in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "LANG")}
        if name == "job":
            res = _run_windows([sys.executable, "-c", PROBE_CODE], cwd, env, 30)
        else:
            res = _run_posix(prefix, name, [sys.executable, "-c", PROBE_CODE], cwd, env, 30)
        ok = res.returncode == 0 and "ETHER_JAIL_OK" in res.stdout
        net = res.stdout.split("ETHER_JAIL_OK", 1)[-1].strip() if ok else ""
        return {"backend": name, "ok": ok, "net": net, "secs": round(time.monotonic() - t0, 2),
                "err": "" if ok else (res.stderr or res.stdout)[-200:]}
    except Exception as exc:
        return {"backend": name, "ok": False, "err": f"{type(exc).__name__}: {str(exc)[:160]}"}
    finally:
        shutil.rmtree(cwd, ignore_errors=True)


def probe(refresh: bool = False) -> Dict[str, Any]:
    """Pick the first backend that runs a trivial child on this machine. Cached per process."""
    if _PROBE and not refresh:
        return dict(_PROBE)
    tried: List[Dict[str, Any]] = []
    chosen = ""
    if os.name == "nt":
        row = _probe_one("job", [])
        tried.append(row)
        chosen = "job" if row["ok"] else ""
    else:
        for name, prefix in _posix_backends(tempfile.gettempdir(), ()):
            row = _probe_one(name, prefix)
            tried.append(row)
            if row["ok"]:
                chosen = name
                break
    _PROBE.clear()
    _PROBE.update({"backend": chosen, "tried": tried, "mode": mode()})
    return dict(_PROBE)


def interpreter(argv: Sequence[str]) -> List[str]:
    """ETHER_GATE_PYTHON (optional): a dedicated interpreter for gate runs, e.g. one blocked by
    scripts/gate_firewall.ps1. Only replaces argv[0] when it is this process's own interpreter."""
    alt = os.getenv("ETHER_GATE_PYTHON", "").strip()
    out = list(argv)
    if alt and out and out[0] == sys.executable:
        out[0] = alt
    return out


def run(argv: Sequence[str], cwd: str, env: Dict[str, str], timeout: Optional[float] = None,
        writable: Sequence[str] = ()) -> Result:
    """Run one gate/scan subprocess under the jail chosen by ETHER_GATE_JAIL."""
    argv = interpreter(argv)
    m = mode()
    if m == "off":
        return _run_plain(argv, cwd, env, timeout, "off")
    info = probe()
    backend = info.get("backend") or ""
    if not backend:
        if m == "on":
            return Result(-7, "", "gate jail required (ETHER_GATE_JAIL=1) but no backend passed the probe",
                          False, "refused", {"probe": info.get("tried")})
        return _run_plain(argv, cwd, env, timeout, "none: no backend passed the probe")
    try:
        if backend == "job":
            return _run_windows(argv, cwd, env, timeout)
        prefix = dict(_posix_backends(cwd, writable)).get(backend, [])
        return _run_posix(prefix, backend, argv, cwd, env, timeout)
    except Exception as exc:
        if m == "on":
            return Result(-7, "", f"gate jail failed: {type(exc).__name__}: {exc}"[:300], False, "refused")
        res = _run_plain(argv, cwd, env, timeout, f"none: {backend} failed ({type(exc).__name__})")
        return res
