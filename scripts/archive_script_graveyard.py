"""Archive one-shot apply_* scripts into scripts/_graveyard/.

SAFE: moves files (git can still recover). Does not touch keepers.

  python -m scripts.archive_script_graveyard --dry-run
  python -m scripts.archive_script_graveyard --apply
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
GRAVEYARD = SCRIPTS / "_graveyard"
REPORT = ROOT / "artifacts" / "script_graveyard_archive.json"

# Explicit list — only known one-shot patch applicators
ARCHIVE_NAMES = [
    "apply_clearquartz_import_fix.py",
    "apply_findings_phase_d.py",
    "apply_findings_phase_e.py",
    "apply_ledger_nudge.py",
    "apply_parse_fix.py",
    "apply_phasec_slice3.py",
    "apply_phased_slice1.py",
    "apply_phased_slice1b.py",
    "apply_phased_slice1b_filescope.py",
    "apply_phased_slice1b_fix.py",
    "apply_phased_slice1b_same_workspace.py",
    "apply_phased_slice1b_shortcircuit.py",
    "apply_phased_slice1b_stabilize.py",
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Actually move files")
    ap.add_argument("--dry-run", action="store_true", default=True)
    args = ap.parse_args(argv)
    do_apply = bool(args.apply)

    moved = []
    missing = []
    GRAVEYARD.mkdir(parents=True, exist_ok=True)
    readme = GRAVEYARD / "README.md"
    if not readme.exists():
        readme.write_text(
            "# Script graveyard\n\n"
            "One-shot apply_* patch scripts archived after their changes landed in core/.\n"
            "Do not run these against current main without audit.\n",
            encoding="utf-8",
        )

    for name in ARCHIVE_NAMES:
        src = SCRIPTS / name
        if not src.is_file():
            missing.append(name)
            continue
        dst = GRAVEYARD / name
        entry = {"name": name, "bytes": src.stat().st_size}
        if do_apply:
            if dst.exists():
                dst = GRAVEYARD / f"{src.stem}_{datetime.now(timezone.utc).strftime('%H%M%S')}.py"
            shutil.move(str(src), str(dst))
            entry["dest"] = str(dst.relative_to(ROOT))
            entry["action"] = "moved"
        else:
            entry["action"] = "would_move"
        moved.append(entry)

    payload = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "applied": do_apply,
        "n_moved": len([m for m in moved if m.get("action") == "moved"]),
        "n_candidates": len(moved),
        "missing": missing,
        "items": moved,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
