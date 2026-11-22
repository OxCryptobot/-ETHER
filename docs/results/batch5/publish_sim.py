"""Batch 5: simulated day of host publishes (commits/hour) with the real throttle and cadence.

    python docs/results/batch5/publish_sim.py [out.json]

Uses scripts.origin_publish.throttled and scripts.host_supervisor.dry_backoff_s as shipped.
One writer pass calls publish twice (start + end of host_main._tick); every un-throttled call
commits (app_alive/ollama_probe timestamps always change). Scenarios:
  old       origin/main today: no throttle, 31 stale non-edit jobs -> BUSY poll 12 s, 19 s pass
  b2_dirty  batch 2: throttle, but a kept code file stays dirty -> every call urgent; 12 s poll
  b5_dirty  batch 5: same dirty file, urgent only if origin would change (it would not); 60 s poll
  b5_dry    batch 5: queue empty -> dry backoff 60..900 s, 19 s pass
  b5_busy   batch 5: real goals, 240 s work passes, 60 s poll, 10% of passes keep an edit (urgent)
"""
from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.host_supervisor import dry_backoff_s  # noqa: E402
from scripts.origin_publish import throttled  # noqa: E402

SCEN = {
    "old": dict(min_s=0.0, poll=12.0, pass_s=19.0, work=False, dirty=False, b5_urgent=False, keep=0.0),
    "b2_dirty": dict(min_s=300.0, poll=12.0, pass_s=240.0, work=True, dirty=True, b5_urgent=False, keep=0.0),
    "b5_dirty": dict(min_s=300.0, poll=60.0, pass_s=240.0, work=True, dirty=True, b5_urgent=True, keep=0.0),
    "b5_dry": dict(min_s=300.0, poll=60.0, pass_s=19.0, work=False, dirty=False, b5_urgent=True, keep=0.0),
    "b5_busy": dict(min_s=300.0, poll=60.0, pass_s=240.0, work=True, dirty=False, b5_urgent=True, keep=0.10),
}


def simulate(name: str, hours: float = 24.0, seed: int = 5) -> dict:
    c = SCEN[name]
    rng = random.Random(seed)
    t0 = datetime(2026, 11, 21, tzinfo=timezone.utc)
    now, end = t0, t0 + timedelta(hours=hours)
    last = ""
    commits = passes = urgent_n = 0
    dry = 0
    while now < end:
        passes += 1
        kept = c["work"] and rng.random() < c["keep"]
        for at in (0.0, c["pass_s"]):  # publish at start and at end of the pass
            t = now + timedelta(seconds=at)
            urgent = (kept and at > 0) or (c["dirty"] and not c["b5_urgent"])
            if not throttled(last, urgent=urgent, now=t, min_s=c["min_s"]) or c["min_s"] == 0:
                commits += 1
                urgent_n += int(urgent)
                last = t.isoformat()
        now += timedelta(seconds=c["pass_s"])
        if c["work"]:
            dry = 0
            wait = c["poll"]
        else:
            dry += 1
            wait = c["poll"] if name == "old" else dry_backoff_s(dry, base=c["poll"])
        now += timedelta(seconds=wait)
    return {"scenario": name, "hours": hours, "passes": passes, "commits": commits,
            "commits_per_hour": round(commits / hours, 1), "urgent_commits": urgent_n, **c}


if __name__ == "__main__":
    rows = [simulate(n) for n in SCEN]
    for r in rows:
        print(f"{r['scenario']:9s} passes={r['passes']:5d} commits={r['commits']:5d} per_hour={r['commits_per_hour']}")
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
