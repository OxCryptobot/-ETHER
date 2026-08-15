"""Archive failed job JSON into failed_archived (queue hygiene)."""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAILED = ROOT / "artifacts" / "jobs" / "failed"
ARCH = ROOT / "artifacts" / "jobs" / "failed_archived"


def main() -> int:
    FAILED.mkdir(parents=True, exist_ok=True)
    ARCH.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%H%M%S")
    moved = 0
    for p in sorted(FAILED.glob("*.json")):
        if p.name == ".gitkeep":
            continue
        dst = ARCH / p.name
        if dst.exists():
            dst = ARCH / f"{p.stem}_{stamp}.json"
        try:
            shutil.move(str(p), str(dst))
            moved += 1
        except OSError as e:
            print(f"skip {p.name}: {e}", flush=True)
    print(f"archived_failed {moved}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
