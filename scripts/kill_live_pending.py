"""Purge residual live-ledger pending jobs (queue hygiene).

Replaces the broken single-line -c STEADY template that SyntaxError'd.
Always exits 0 so continue_on_fail hygiene stays quiet.
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PENDING = ROOT / "artifacts" / "jobs" / "pending"
ARCH = ROOT / "artifacts" / "jobs" / "failed_archived"


def main() -> int:
    PENDING.mkdir(parents=True, exist_ok=True)
    ARCH.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%H%M%S")
    killed = 0
    patterns = ("ss_pipeline_ledger_*.json", "*live*ledger*.json")
    seen: set[Path] = set()
    for pat in patterns:
        for p in PENDING.glob(pat):
            if p in seen or p.name == ".gitkeep":
                continue
            seen.add(p)
            dst = ARCH / f"{p.stem}_killed_{stamp}.json"
            if dst.exists():
                dst = ARCH / f"{p.stem}_killed_{stamp}_{killed}.json"
            try:
                shutil.move(str(p), str(dst))
                killed += 1
            except OSError as e:
                print(f"skip {p.name}: {e}", flush=True)
    print(f"killed_live_pending {killed}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
