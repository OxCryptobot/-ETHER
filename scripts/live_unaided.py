#!/usr/bin/env python3
"""Unaided expansion runner.

FAST default: prove the seed is hard (pytest red).
--live: bounded craft walk (bug_comments → replace_once). Not Pipeline.run
(walk_lru timed out rc=124 on the 76kB god-file). Not a living-gate count.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
sys.path.insert(0, str(ROOT))


def seed_is_hard(name: str) -> dict:
    from core.loop.living import FIXTURES, run_tests

    ws = FIXTURES[name]
    if not ws.exists():
        return {"ok": False, "error": "missing", "name": name}
    tests = run_tests(workspace=ws, timeout=45)
    hard = tests.get("ok") is not True
    return {
        "ok": hard,
        "name": name,
        "hard": hard,
        "tests_ok": tests.get("ok"),
        "workspace": str(ws),
        "note": "seed must FAIL pytest so unaided LIVE has something to fix",
    }


def run_live(name: str) -> dict:
    from core.loop.walk_fixture import walk_bounded

    return walk_bounded(name, timeout=45)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("fixture", choices=["lru", "topo", "intervals", "merge", "ledger"])
    p.add_argument("--live", action="store_true")
    args = p.parse_args()
    if args.live:
        out = run_live(args.fixture)
    else:
        out = seed_is_hard(args.fixture)
    print(json.dumps(out, indent=2, default=str), flush=True)
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
