#!/usr/bin/env python3
"""Run automated @ETHER health checks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.dotenv import load_dotenv
from core.health_check import format_report, run_health_checks

load_dotenv(ROOT / ".env")


def main() -> int:
    ap = argparse.ArgumentParser(description="@ETHER automated health checks")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--skip-sandbox", action="store_true", help="Skip live sandbox smoke")
    ap.add_argument("--strict", action="store_true", help="Exit 1 on any non-ok status")
    args = ap.parse_args()

    report = run_health_checks(include_sandbox_smoke=not args.skip_sandbox)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_report(report))

    status = report.get("status")
    if args.strict:
        return 0 if status == "ok" else 1
    # default: fail only on critical
    return 0 if status != "critical" else 1


if __name__ == "__main__":
    raise SystemExit(main())
