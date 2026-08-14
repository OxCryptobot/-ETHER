"""List one-shot apply_*/build_* scripts for graveyard purge decisions.

Does NOT delete. Writes artifacts/script_graveyard_inventory.json.

  python -m scripts.inventory_script_graveyard
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
OUT = ROOT / "artifacts" / "script_graveyard_inventory.json"

PATTERNS = [
    re.compile(r"^apply_.*\.py$"),
    re.compile(r"^build_.*\.py$"),
    re.compile(r"^patch_.*\.py$"),
    re.compile(r"^one_shot_.*\.py$"),
    re.compile(r"^tmp_.*\.py$"),
]

# Keep these even if they match patterns
KEEP = {
    "batch_phase_d.py",
    "batch_phase_f.py",
    "host_agent.py",
    "foreman.py",
    "measure_tool_runtime.py",
    "pep8_review.py",
    "ether_cli.py",
    "start_ether_host.ps1",
    "inventory_script_graveyard.py",
}


def main() -> int:
    candidates = []
    keepers = []
    if SCRIPTS.is_dir():
        for p in sorted(SCRIPTS.glob("*.py")):
            name = p.name
            if name in KEEP:
                keepers.append(name)
                continue
            if any(rx.match(name) for rx in PATTERNS):
                candidates.append(
                    {
                        "name": name,
                        "bytes": p.stat().st_size,
                        "action": "archive_candidate",
                    }
                )
            else:
                keepers.append(name)
    payload = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "n_candidates": len(candidates),
        "n_keepers": len(keepers),
        "candidates": candidates,
        "note": "Do not delete until measurements are in scoreboards/FINDINGS.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"candidates={len(candidates)} keepers={len(keepers)}")
    print(f"wrote {OUT}")
    for c in candidates[:40]:
        print(f"  ARCHIVE? {c['name']} ({c['bytes']} bytes)")
    if len(candidates) > 40:
        print(f"  ... +{len(candidates) - 40} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
