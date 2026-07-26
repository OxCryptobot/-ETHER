#!/usr/bin/env python3
"""CLI: reconcile quarantine tools into persistent or discard duplicates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.tool_reconcile import reconcile


def main() -> int:
    p = argparse.ArgumentParser(description="@ETHER quarantine tool reconciler")
    p.add_argument("--dry-run", action="store_true", help="report only, no file changes")
    p.add_argument("--threshold", type=float, default=0.82, help="duplicate similarity cutoff")
    p.add_argument("--max-promote", type=int, default=25)
    args = p.parse_args()
    report = reconcile(
        promote_threshold=args.threshold,
        dry_run=args.dry_run,
        max_promote=args.max_promote,
    )
    print(json.dumps({
        "promoted": report["promoted"],
        "discarded": report["discarded"],
        "kept": report["kept"],
        "quarantine_before": report["quarantine_before"],
        "persistent_count": report["persistent_count"],
        "dry_run": report["dry_run"],
        "actions": report["actions"][:30],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
