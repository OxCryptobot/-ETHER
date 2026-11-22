"""Batch 10 item 2: OS-level jail for honest-gate runs (core/agent/gate_jail.py)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from core.agent import gate_jail as gj


@pytest.fixture(autouse=True)
def _fresh_probe(monkeypatch):
    gj._PROBE.clear()
    yield
    gj._PROBE.clear()


def test_mode_parsing(monkeypatch):
    for raw, want in (("", "auto"), ("auto", "auto"), ("1", "on"), ("on", "on"), ("0", "off"), ("off", "off"),
                      ("weird", "auto")):
        monkeypatch.setenv("ETHER_GATE_JAIL", raw)
        assert gj.mode() == want
    monkeypatch.delenv("ETHER_GATE_JAIL")
    assert gj.mode() == "auto"


def test_job_limits_are_the_documented_numbers(monkeypatch):
    monkeypatch.setenv("ETHER_GATE_JAIL_MEM_MB", "2048")
    monkeypatch.setenv("ETHER_GATE_JAIL_PROCS", "16")
    monkeypatch.delenv("ETHER_GATE_JAIL_CPU_S", raising=False)
    lim = gj.job_limits(100)
    assert lim["job_memory"] == 2048 * 1024 * 1024
    assert lim["active_processes"] == 16
    assert lim["job_time_100ns"] == (100 * 2 + 30) * 10_000_000
    for flag in (gj.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, gj.JOB_OBJECT_LIMIT_ACTIVE_PROCESS,
                 gj.JOB_OBJECT_LIMIT_JOB_MEMORY, gj.JOB_OBJECT_LIMIT_JOB_TIME):
        assert lim["flags"] & flag


def test_off_runs_plain(monkeypatch, tmp_path):
    monkeypatch.setenv("ETHER_GATE_JAIL", "off")
    r = gj.run([sys.executable, "-c", "print('hi')"], str(tmp_path), dict(os.environ), 30)
    assert r.returncode == 0 and r.stdout.strip() == "hi" and r.jail == "off"


def test_required_jail_without_backend_refuses(monkeypatch, tmp_path):
    monkeypatch.setenv("ETHER_GATE_JAIL", "1")
    monkeypatch.setattr(gj, "probe", lambda refresh=False: {"backend": "", "tried": [], "mode": "on"})
    r = gj.run([sys.executable, "-c", "print('hi')"], str(tmp_path), dict(os.environ), 30)
    assert r.returncode == -7 and r.jail == "refused" and "hi" not in r.stdout


def test_auto_without_backend_is_batch9_behaviour_and_says_so(monkeypatch, tmp_path):
    monkeypatch.setenv("ETHER_GATE_JAIL", "auto")
    monkeypatch.setattr(gj, "probe", lambda refresh=False: {"backend": "", "tried": [], "mode": "auto"})
    r = gj.run([sys.executable, "-c", "print('hi')"], str(tmp_path), dict(os.environ), 30)
    assert r.returncode == 0 and r.jail.startswith("none")


posix = pytest.mark.skipif(os.name == "nt", reason="posix backends")


@posix
def test_probe_picks_a_backend_on_this_machine():
    info = gj.probe(refresh=True)
    assert info["backend"] in ("bwrap", "unshare", "rlimit")
    assert info["tried"][-1]["ok"]


@posix
def test_timeout_kills_the_whole_group(monkeypatch, tmp_path):
    monkeypatch.setenv("ETHER_GATE_JAIL", "auto")
    code = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); time.sleep(60)"
    r = gj.run([sys.executable, "-c", code], str(tmp_path), dict(os.environ), 2)
    assert r.timed_out and r.returncode == -9


@posix
def test_memory_cap_applies(monkeypatch, tmp_path):
    monkeypatch.setenv("ETHER_GATE_JAIL", "auto")
    monkeypatch.setenv("ETHER_GATE_JAIL_MEM_MB", "512")
    r = gj.run([sys.executable, "-c", "x = bytearray(2 * 1024 ** 3)"], str(tmp_path), dict(os.environ), 60)
    assert r.returncode != 0 and "MemoryError" in r.stderr


@posix
def test_strong_backends_block_network_and_outside_writes(monkeypatch, tmp_path):
    monkeypatch.setenv("ETHER_GATE_JAIL", "auto")
    info = gj.probe(refresh=True)
    if info["backend"] not in ("bwrap", "unshare"):
        pytest.skip("no namespace backend on this machine")
    assert info["tried"][-1]["net"] == "blocked"
    if info["backend"] == "bwrap":
        outside = Path(__file__).resolve().parents[1] / "ether_jail_escape.txt"
        code = f"open({str(outside)!r}, 'w').write('x')"
        r = gj.run([sys.executable, "-c", code], str(tmp_path), dict(os.environ), 30)
        assert r.returncode != 0 and not outside.exists()
        ok = gj.run([sys.executable, "-c", "open('inside.txt','w').write('x')"], str(tmp_path), dict(os.environ), 30)
        assert ok.returncode == 0 and (tmp_path / "inside.txt").exists()


# ------------------------------------------------------------------ windows path, mocked

class _FakeJob:
    def __init__(self, timeout):
        self.limits = gj.job_limits(timeout)
        self.calls = []

    def assign(self, handle):
        self.calls.append(("assign", handle))

    def terminate(self):
        self.calls.append(("terminate",))

    def close(self):
        self.calls.append(("close",))


class _FakeProc:
    def __init__(self, argv, hang=False, **kw):
        self.kw = kw
        self._handle = 4242
        self.returncode = 0
        self.hang = hang
        self.killed = False

    def communicate(self, timeout=None):
        if self.hang and timeout is not None:
            raise subprocess.TimeoutExpired("x", timeout)
        return ("out", "")

    def kill(self):
        self.killed = True


def test_windows_child_is_created_suspended_assigned_then_resumed():
    jobs, procs = [], []

    def factory(t):
        jobs.append(_FakeJob(t))
        return jobs[-1]

    def popen(argv, **kw):
        procs.append(_FakeProc(argv, **kw))
        return procs[-1]

    resumed = []
    r = gj._run_windows(["py"], "C:/m", {}, 10, job_factory=factory, popen=popen,
                        resume=lambda p: resumed.append(p._handle) or 0)
    assert r.returncode == 0 and r.jail == "job"
    assert procs[0].kw["creationflags"] & gj.CREATE_SUSPENDED
    assert jobs[0].calls[0] == ("assign", 4242) and resumed == [4242]
    assert jobs[0].calls[-1] == ("close",)  # kill-on-close reaps grandchildren


def test_windows_timeout_terminates_the_job():
    job = _FakeJob(1)
    r = gj._run_windows(["py"], "C:/m", {}, 1, job_factory=lambda t: job,
                        popen=lambda a, **k: _FakeProc(a, hang=True, **k), resume=lambda p: 0)
    assert r.timed_out and ("terminate",) in job.calls and job.calls[-1] == ("close",)


def test_windows_failed_resume_kills_child_and_raises():
    job = _FakeJob(1)
    holder = {}

    def popen(a, **k):
        holder["p"] = _FakeProc(a, **k)
        return holder["p"]

    with pytest.raises(OSError):
        gj._run_windows(["py"], "C:/m", {}, 1, job_factory=lambda t: job, popen=popen, resume=lambda p: 0xC0000001)
    assert holder["p"].killed and job.calls[-1] == ("close",)


def test_winjob_sets_extended_limits_with_fake_kernel32():
    pytest.importorskip("ctypes.wintypes")
    import ctypes

    class K32:
        def __init__(self):
            self.infos = []

        def CreateJobObjectW(self, a, b):
            return 77

        def SetInformationJobObject(self, h, cls, ptr, size):
            self.infos.append((cls, size, ctypes.cast(ptr, ctypes.c_void_p)))
            return 1

        def AssignProcessToJobObject(self, h, p):
            return 0

        def TerminateJobObject(self, h, code):
            return 1

        def CloseHandle(self, h):
            self.closed = h
            return 1

    k = K32()
    job = gj.WinJob(30, k32=k)
    classes = [i[0] for i in k.infos]
    assert classes == [gj.JobObjectExtendedLimitInformation, gj.JobObjectBasicUIRestrictions]
    with pytest.raises(OSError):
        job.assign(5)  # AssignProcessToJobObject returned 0
    job.close()
    assert k.closed == 77 and job.handle is None


def test_winjob_closes_handle_when_limits_fail():
    pytest.importorskip("ctypes.wintypes")

    class K32:
        closed = None

        def CreateJobObjectW(self, a, b):
            return 9

        def SetInformationJobObject(self, *a):
            return 0

        def CloseHandle(self, h):
            K32.closed = h

    with pytest.raises(OSError):
        gj.WinJob(30, k32=K32())
    assert K32.closed == 9


def test_auto_falls_back_when_the_backend_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("ETHER_GATE_JAIL", "auto")
    monkeypatch.setattr(gj, "probe", lambda refresh=False: {"backend": "job", "tried": [], "mode": "auto"})

    def boom(*a, **k):
        raise OSError("no job")

    monkeypatch.setattr(gj, "_run_windows", boom)
    r = gj.run([sys.executable, "-c", "print('hi')"], str(tmp_path), dict(os.environ), 30)
    assert r.returncode == 0 and r.jail.startswith("none: job failed")
    monkeypatch.setenv("ETHER_GATE_JAIL", "1")
    r = gj.run([sys.executable, "-c", "print('hi')"], str(tmp_path), dict(os.environ), 30)
    assert r.returncode == -7 and r.jail == "refused"


# ------------------------------------------------------------------ gate integration

def test_gate_run_records_the_jail_and_refusal_aborts(monkeypatch, tmp_path):
    from core.agent import goal_source as gs

    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    monkeypatch.setenv("ETHER_GATE_SANDBOX_DIR", str(tmp_path.parent / (tmp_path.name + "_box")))
    res = gs.run_pytest(tmp_path, ["tests/test_x.py"], timeout=120)
    assert res["status"] and "jail" in res
    monkeypatch.setenv("ETHER_GATE_JAIL", "1")
    monkeypatch.setattr(gj, "probe", lambda refresh=False: {"backend": "", "tried": [], "mode": "on"})
    res = gs.run_pytest(tmp_path, ["tests/test_x.py"], timeout=120)
    assert res["rc"] == -7 and gs.baseline_abort(res).startswith("sandbox error: gate jail refused")


def test_required_jail_without_backend_is_a_health_signal():
    from scripts.host_signals import host_signals

    row = {"selfcheck": {"ok": True, "gate_jail": {"mode": "on", "backend": "none"}}}
    assert any(s["name"] == "gate_jail" for s in host_signals(row))
    row["selfcheck"]["gate_jail"] = {"mode": "auto", "backend": "none"}
    assert not any(s["name"] == "gate_jail" for s in host_signals(row))


def test_firewall_script_is_opt_in_and_never_run_by_code():
    ps1 = Path("scripts/gate_firewall.ps1").read_text(encoding="utf-8")
    assert "#Requires -RunAsAdministrator" in ps1 and "New-NetFirewallRule" in ps1
    for rel in ("scripts/host_main.py", "scripts/host_supervisor.py", "scripts/host.cmd"):
        assert "gate_firewall" not in Path(rel).read_text(encoding="utf-8")


def test_gate_python_override_only_replaces_the_interpreter(monkeypatch):
    monkeypatch.setenv("ETHER_GATE_PYTHON", "/opt/gatepy")
    assert gj.interpreter([sys.executable, "-m", "pytest"]) == ["/opt/gatepy", "-m", "pytest"]
    assert gj.interpreter(["ruff", "check"]) == ["ruff", "check"]
    monkeypatch.delenv("ETHER_GATE_PYTHON")
    assert gj.interpreter([sys.executable, "-m", "pytest"])[0] == sys.executable
