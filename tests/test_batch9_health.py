"""Batch 9 item 3: worst-signal health; pull failures count; diverged clone gets a manual fix."""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.host_signals import diverged, host_signals, pull_signals, worst, write_diverged
from scripts.host_supervisor import Supervisor, paths


def _sup(tmp_path, pull_rows, run_row=None, diverge=None, cycles=1):
    it = iter(pull_rows)
    sleeps = []
    sup = Supervisor(tmp_path, pull=lambda b: dict(next(it)), run=lambda b: dict(run_row or {"ok": True, "rc": 0}),
                     ollama=lambda: {"ok": True}, sleep=sleeps.append, idle=lambda: 5.0, max_cycles=cycles,
                     work=lambda b: True, diverge=diverge or (lambda b: {"ok": True, "ahead": 1, "behind": 3,
                                                                          "artifacts_only": True, "fix": "FIX"}))
    return sup


def _state(tmp_path):
    return json.loads(paths(tmp_path)["state"].read_text(encoding="utf-8"))


def test_failed_pull_is_not_zero_failures(tmp_path):
    sup = _sup(tmp_path, [{"ok": False, "rc": 128}] * 4, cycles=4)
    seen = []
    orig = sup.write_state
    sup.write_state = lambda st, extra=None: (seen.append((sup.health.get("health"), sup.pull_failures)), orig(st, extra))[1]
    sup.loop()
    st = _state(tmp_path)
    assert st["pull_failures"] == 4 and st["health"] == "failing"
    assert "git pull failed (rc 128)" in st["health_worst"] and "FIX" in st["health_worst"]
    assert ("degraded", 1) in seen  # one failed pull: degraded, three in a row: failing
    info = json.loads((tmp_path / "artifacts" / "pull_diverged.json").read_text(encoding="utf-8"))
    assert info["fix"] == "FIX" and info["streak"] == 4


def test_pull_recovers_and_clears_the_diverged_note(tmp_path):
    sup = _sup(tmp_path, [{"ok": False, "rc": 128}, {"ok": True, "moved": False}], cycles=2)
    sup.loop()
    assert _state(tmp_path)["pull_failures"] == 0
    assert not (tmp_path / "artifacts" / "pull_diverged.json").exists()


def test_host_signals_queue_empty_plan_error_and_stale_sota(tmp_path):
    now = datetime.now(timezone.utc)
    art = tmp_path / "artifacts"
    art.mkdir()
    (art / "sota.json").write_text(json.dumps({"last": {"ts": (now - timedelta(days=3)).isoformat()}}), encoding="utf-8")
    host = {"ts": now.isoformat(), "next_goal": "none", "sota": {"note": "queue empty"},
            "plan_error": "ImportError: cannot import name 'heartbeat_plan'"}
    names = {s["name"]: s["level"] for s in host_signals(host, base=tmp_path)}
    assert names == {"plan_error": "degraded", "queue": "degraded", "sota_stale": "degraded"}
    w = worst(host_signals({**host, "selfcheck_error": "x"}, base=tmp_path))
    assert w["health"] == "failing" and w["worst"].startswith("selfcheck")
    assert worst([])["health"] == "ok"


def test_supervisor_reads_host_main_for_health(tmp_path):
    art = tmp_path / "artifacts"
    art.mkdir()
    (art / "host_main.json").write_text(json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                                                    "sota": {"note": "queue empty"}, "next_goal": "none"}),
                                        encoding="utf-8")
    sup = _sup(tmp_path, [{"ok": True, "moved": False}])
    sup.loop()
    st = _state(tmp_path)
    assert st["health"] == "degraded" and st["health_worst"].startswith("queue")


def test_host_main_row_reports_worst(tmp_path):
    from scripts import host_main

    row = {"ts": datetime.now(timezone.utc).isoformat(), "sota": {"note": "queue empty"},
           "runtime_error": "ImportError: x"}
    host_main._write_row(tmp_path, row)
    disk = json.loads((tmp_path / "artifacts" / "host_main.json").read_text(encoding="utf-8"))
    assert disk["health"] == "degraded" and {s["name"] for s in disk["health_signals"]} == {"runtime_error", "queue"}


def test_pull_signal_levels():
    assert pull_signals({"ok": True}, 0) == []
    assert pull_signals({"ok": False, "rc": 1}, 1)[0]["level"] == "degraded"
    assert pull_signals({"ok": False, "rc": 1}, 3)[0]["level"] == "failing"


# ---------------------------------------------------------------- real git, read-only detector

def _git(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, env=env, check=True).stdout.strip()


def _diverged_clone(tmp_path: Path, local_file: str) -> Path:
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    seed = tmp_path / "seed"
    _git(tmp_path, "clone", "-q", str(origin), str(seed))
    (seed / "artifacts").mkdir()
    (seed / "artifacts" / "a.json").write_text("{}", encoding="utf-8")
    (seed / "core.py").write_text("X = 1\n", encoding="utf-8")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-qm", "seed")
    _git(seed, "push", "-q", "origin", "HEAD:main")
    host = tmp_path / "host"
    _git(tmp_path, "clone", "-q", str(origin), str(host))
    (seed / "core.py").write_text("X = 2\n", encoding="utf-8")
    _git(seed, "commit", "-qam", "upstream code")
    _git(seed, "push", "-q", "origin", "HEAD:main")
    (host / local_file).write_text('{"local": 1}\n', encoding="utf-8")
    _git(host, "add", "-A")
    _git(host, "commit", "-qm", "local heartbeat")
    _git(host, "fetch", "-q", "origin")
    return host


def test_diverged_artifacts_only_offers_reset_keep_but_never_runs_it(tmp_path):
    host = _diverged_clone(tmp_path, "artifacts/a.json")
    head = _git(host, "rev-parse", "HEAD")
    info = diverged(host)
    assert info["diverged"] and info["ahead"] == 1 and info["behind"] == 1 and info["artifacts_only"] is True
    assert "git reset --keep origin/main" in info["fix"] and "not automatic" in info["fix"]
    write_diverged(host, info)
    assert _git(host, "rev-parse", "HEAD") == head  # read-only: nothing reset


def test_diverged_with_code_says_do_not_reset(tmp_path):
    host = _diverged_clone(tmp_path, "local_code.py")
    info = diverged(host)
    assert info["artifacts_only"] is False and "Do NOT reset" in info["fix"] and "local_code.py" in info["fix"]
