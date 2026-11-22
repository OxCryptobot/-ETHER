"""Batch 9 item 4: telemetry out of git (audit W17, W61)."""
from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone

MEASURED_COMMITS_24H = 5452  # origin/main, 2026-11-22 (docs/AUDIT_FULL_2026-11-22.md section 2)


def test_publish_whitelist_is_small_and_has_no_stale_exe_entries():
    from scripts import origin_publish as op

    assert op.PATHS == op.TELEMETRY_PATHS
    assert not any("exe_" in p for p in op.PATHS)
    assert "artifacts/goal_index.json" not in op.PATHS  # rewritten every attempt: local only
    for need in ("artifacts/host_main.json", "artifacts/supervisor.json", "artifacts/learning_summary.json",
                 "artifacts/unison.json", "artifacts/app_alive.json", "artifacts/pull_diverged.json"):
        assert need in op.PATHS
    assert len(op.PATHS) <= 10 and all(p.startswith("artifacts/") for p in op.PATHS)


def test_legacy_list_only_on_request(monkeypatch):
    from scripts import origin_publish as op

    monkeypatch.setenv("ETHER_PUBLISH_PATHS", "legacy")
    try:
        mod = importlib.reload(op)
        assert "artifacts/goal_index.json" in mod.PATHS and not any("exe_" in p for p in mod.PATHS)
    finally:
        monkeypatch.delenv("ETHER_PUBLISH_PATHS")
        importlib.reload(op)


def _simulate(pass_every_s: float, kept_per_day: int = 0) -> int:
    """Heartbeat publishes in 24 h with the throttle, one pass every pass_every_s (two publish calls/pass)."""
    from scripts.origin_publish import PUBLISH_MIN_S, throttled

    t0 = datetime(2026, 11, 22, tzinfo=timezone.utc)
    last = ""
    commits = 0
    kept_at = {int(i * 86400 / kept_per_day) // int(pass_every_s) for i in range(kept_per_day)} if kept_per_day else set()
    n = int(86400 / pass_every_s)
    for i in range(n):
        now = t0 + timedelta(seconds=i * pass_every_s)
        for _call in range(2):
            urgent = i in kept_at and _call == 1
            if not throttled(last, urgent=urgent, now=now, min_s=PUBLISH_MIN_S):
                commits += 1
                last = now.isoformat()
    return commits


def test_commits_per_day_cut_by_more_than_95_percent():
    from scripts.origin_publish import PUBLISH_MIN_S

    assert PUBLISH_MIN_S >= 1800
    busy = _simulate(32)  # the batch 5 measurement: one pass every ~32 s
    assert busy <= 49
    with_kept = _simulate(32, kept_per_day=40)  # kept edits are urgent and bypass the throttle
    assert with_kept <= 49 + 40
    assert 1 - with_kept / MEASURED_COMMITS_24H > 0.95


def test_kept_edit_is_still_urgent():
    from scripts.origin_publish import throttled

    now = datetime(2026, 11, 22, 12, tzinfo=timezone.utc)
    recent = (now - timedelta(seconds=30)).isoformat()
    assert throttled(recent, urgent=False, now=now) is True
    assert throttled(recent, urgent=True, now=now) is False
