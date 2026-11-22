"""Batch 2: the worktree publish must not revert upstream code (clobber guard)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.origin_publish import code_paths_upstream_changed


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)


def _runner(cwd: Path):
    def run(argv):
        return subprocess.run(argv[:1] + ["-C", str(cwd)] + argv[1:], capture_output=True, text=True)
    return run


def test_upstream_change_is_never_copied_over(tmp_path: Path) -> None:
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    a = tmp_path / "a"
    subprocess.run(["git", "clone", "-q", str(origin), str(a)], check=True)
    for k, v in (("user.name", "t"), ("user.email", "t@t")):
        _git(a, "config", k, v)
    (a / "core").mkdir()
    (a / "core" / "plan.py").write_text("def heartbeat_plan():\n    return 1\n")
    (a / "core" / "mine.py").write_text("X = 1\n")
    (a / "artifacts").mkdir()
    (a / "artifacts" / "x.json").write_text("{}\n")
    _git(a, "add", "-A"); _git(a, "commit", "-qm", "base"); _git(a, "push", "-q", "origin", "HEAD:main")
    b = tmp_path / "b"
    subprocess.run(["git", "clone", "-q", str(origin), str(b)], check=True)
    for k, v in (("user.name", "t"), ("user.email", "t@t")):
        _git(b, "config", k, v)
    (b / "core" / "plan.py").write_text("def heartbeat_plan():\n    return 2  # upstream fix\n")
    _git(b, "commit", "-qam", "fix"); _git(b, "push", "-q", "origin", "HEAD:main")
    (a / "core" / "mine.py").write_text("X = 2\n")
    _git(a, "commit", "-qam", "local"); _git(a, "fetch", "-q", "origin")
    skipped = code_paths_upstream_changed("git", _runner(a), ["core/plan.py", "core/mine.py", "artifacts/x.json"])
    assert skipped == ["core/plan.py"]


def test_heartbeat_publish_is_throttled_but_a_kept_edit_is_not() -> None:
    from datetime import datetime, timedelta, timezone

    from scripts.origin_publish import throttled

    now = datetime(2026, 11, 19, 22, 30, tzinfo=timezone.utc)
    recent = (now - timedelta(seconds=60)).isoformat()
    old = (now - timedelta(seconds=900)).isoformat()
    assert throttled(recent, urgent=False, now=now, min_s=300) is True
    assert throttled(recent, urgent=True, now=now, min_s=300) is False
    assert throttled(old, urgent=False, now=now, min_s=300) is False
    assert throttled("", urgent=False, now=now, min_s=300) is False


def test_supervisor_backs_off_when_the_queue_is_empty(tmp_path: Path) -> None:
    from scripts.host_supervisor import Supervisor, dry_backoff_s

    waits = []
    sup = Supervisor(tmp_path, pull=lambda b: {"ok": True}, run=lambda b: {"ok": True, "rc": 0},
                     ollama=lambda: {"ok": True}, changed=lambda *a: False, relaunch=lambda b: {},
                     sleep=lambda s: None, idle=lambda: 12.0, max_cycles=4, work=lambda b: False)
    orig = sup.nap
    sup.nap = lambda secs: (waits.append(secs), orig(0))[1]
    assert sup.loop() == 0
    assert waits == [60.0, 120.0, 240.0]
    assert dry_backoff_s(10) == 900.0
    busy = Supervisor(tmp_path / "b", pull=lambda b: {"ok": True}, run=lambda b: {"ok": True, "rc": 0},
                      ollama=lambda: {"ok": True}, changed=lambda *a: False, relaunch=lambda b: {},
                      sleep=lambda s: None, idle=lambda: 12.0, max_cycles=2, work=lambda b: True)
    seen = []
    busy.nap = lambda secs: seen.append(secs)
    busy.loop()
    assert seen == [12.0]
