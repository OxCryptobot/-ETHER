"""ETHER-Host supervisor: singleton, backoff, heartbeat, tick invocation, sticky stop. Linux-safe."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from scripts.host_lock import HostLock, is_locked, lock_pid
from scripts.host_supervisor import Supervisor, backoff_s, clear_stale_git_lock, paths


def _sup(tmp_path: Path, results, **kw):
    calls = {"pull": 0, "run": 0, "ollama": 0, "sleep": []}

    def pull(base):
        calls["pull"] += 1
        return {"ok": True, "moved": False}

    def run(base):
        calls["run"] += 1
        return results[min(calls["run"], len(results)) - 1]

    def ollama():
        calls["ollama"] += 1
        return {"ok": True}

    sup = Supervisor(tmp_path, pull=pull, run=run, ollama=ollama, sleep=calls["sleep"].append,
                     idle=lambda: 5.0, **kw)
    return sup, calls


def test_lock_is_exclusive_and_released(tmp_path: Path) -> None:
    p = tmp_path / "artifacts" / "host.lock"
    a, b = HostLock(p), HostLock(p)
    assert a.acquire() is True
    assert b.acquire() is False
    assert is_locked(p) is True
    assert lock_pid(p) == os.getpid()
    a.release()
    assert is_locked(p) is False
    assert b.acquire() is True
    b.release()


def test_singleton_second_supervisor_exits(tmp_path: Path) -> None:
    holder = HostLock(paths(tmp_path)["lock"])
    assert holder.acquire()
    try:
        sup, calls = _sup(tmp_path, [{"ok": True}], max_cycles=1)
        assert sup.loop() == 3
        assert calls["run"] == 0  # never a second writer pass
    finally:
        holder.release()


def test_each_cycle_pulls_ensures_ollama_then_runs_one_pass(tmp_path: Path) -> None:
    sup, calls = _sup(tmp_path, [{"ok": True}], max_cycles=3)
    assert sup.loop() == 0
    assert calls == {"pull": 3, "run": 3, "ollama": 3, "sleep": calls["sleep"]}
    assert not is_locked(paths(tmp_path)["lock"])  # released on exit


def test_heartbeat_written_and_honest(tmp_path: Path) -> None:
    sup, _ = _sup(tmp_path, [{"ok": True}], max_cycles=1)
    sup.loop()
    state = json.loads(paths(tmp_path)["state"].read_text(encoding="utf-8"))
    assert state["state"] == "stopped"
    assert state["cycle"] == 1
    assert state["pid"] == os.getpid()
    # The supervisor never writes app_alive: an open process is not a heartbeat.
    assert not (tmp_path / "artifacts" / "app_alive.json").exists()


def test_backoff_grows_and_caps() -> None:
    assert backoff_s(0) == 0
    assert backoff_s(1, base=15, cap=900) == 15
    assert backoff_s(2, base=15, cap=900) == 30
    assert backoff_s(3, base=15, cap=900) == 60
    assert backoff_s(20, base=15, cap=900) == 900


def test_crash_triggers_backoff_then_success_resets(tmp_path: Path) -> None:
    seen = []
    results = [{"ok": False, "rc": 1}, {"ok": False, "rc": -9}, {"ok": True, "rc": 0}]
    sup, calls = _sup(tmp_path, results, max_cycles=3)
    orig = sup.write_state

    def spy(state, extra=None):
        if extra and "next_in_s" in extra:
            seen.append((state, extra["next_in_s"], sup.failures))
        return orig(state, extra)

    sup.write_state = spy
    sup.loop()
    assert seen[0][0] == "backoff" and seen[0][2] == 1
    assert seen[1][0] == "backoff" and seen[1][1] > seen[0][1]
    assert seen[2] == ("running", 5.0, 0)


def test_stop_file_is_sticky(tmp_path: Path) -> None:
    p = paths(tmp_path)
    p["art"].mkdir(parents=True)
    p["stop"].write_text("x", encoding="utf-8")
    sup, calls = _sup(tmp_path, [{"ok": True}], max_cycles=5)
    assert sup.loop() == 0
    assert calls["run"] == 0
    assert p["stop"].is_file()  # the 5-min ensure trigger must not undo a stop


def test_stop_file_mid_nap_ends_loop(tmp_path: Path) -> None:
    sup, calls = _sup(tmp_path, [{"ok": True}])
    p = paths(tmp_path)

    def sleeper(secs):
        p["stop"].write_text("x", encoding="utf-8")

    sup._sleep = sleeper
    assert sup.loop() == 0
    assert calls["run"] == 1


def test_self_update_relaunches_fresh_copy(tmp_path: Path) -> None:
    relaunched = []
    sup = Supervisor(
        tmp_path,
        pull=lambda b: {"ok": True, "moved": True, "before": "a", "after": "b"},
        run=lambda b: {"ok": True},
        ollama=lambda: {"ok": True},
        changed=lambda b, x, y: True,
        relaunch=lambda b: relaunched.append(b) or {"ok": True},
        sleep=lambda s: None,
        idle=lambda: 1.0,
    )
    assert sup.loop() == 0
    assert relaunched == [tmp_path]
    assert not is_locked(paths(tmp_path)["lock"])


def test_real_pass_invokes_host_main_in_child(tmp_path: Path) -> None:
    """run_pass runs `python -m scripts.host_main` (the writer tick) as a child process."""
    from scripts import host_supervisor as hs

    captured = {}

    class P:
        returncode = 0
        stderr = ""

    def fake_run(argv, **kw):
        captured["argv"], captured["env"] = argv, kw.get("env")
        return P()

    orig = hs.subprocess.run
    hs.subprocess.run = fake_run
    try:
        out = hs.run_pass(tmp_path)
    finally:
        hs.subprocess.run = orig
    assert out["ok"] is True
    assert captured["argv"][-2:] == ["-m", "scripts.host_main"]
    assert captured["env"]["ETHER_SUPERVISOR"] == "1"
    assert "GITHUB_ACTIONS" not in captured["env"]


def test_stale_git_index_lock_is_repaired(tmp_path: Path) -> None:
    lock = tmp_path / ".git" / "index.lock"
    lock.parent.mkdir()
    lock.write_text("", encoding="utf-8")
    assert clear_stale_git_lock(tmp_path) is False  # fresh lock: a git may be running
    old = time.time() - 3600
    os.utime(lock, (old, old))
    assert clear_stale_git_lock(tmp_path) is True
    assert not lock.exists()


def test_tick_is_serialised_across_processes(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "scripts").mkdir()
    monkeypatch.setenv("ETHER_ROOT", str(tmp_path))
    from scripts.host_main import tick

    holder = HostLock(tmp_path / "artifacts" / "tick.lock")
    assert holder.acquire()
    try:
        out = tick()
        assert out["note"] == "tick_busy"
        assert not (tmp_path / "artifacts" / "host_main.json").exists()
    finally:
        holder.release()


def test_supervisor_flag_means_no_daemon_spawn(tmp_path: Path, monkeypatch) -> None:
    from scripts.host_main import _ensure_daemon

    monkeypatch.delenv("ETHER_IN_DAEMON", raising=False)
    monkeypatch.setenv("ETHER_SUPERVISOR", "1")
    assert _ensure_daemon(tmp_path) == {"ok": True, "note": "supervisor_owns_loop"}


def test_retired_keepalive_name_lands_in_supervisor() -> None:
    import scripts.ether_keepalive as legacy
    import scripts.host_supervisor as sup

    assert legacy.main is sup.main
    assert legacy.tick is sup.tick
