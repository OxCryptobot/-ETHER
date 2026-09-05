#!/usr/bin/env python3
"""Unaided LIVE runner for a named fixture. FAST default: prove the seed is hard.

--live: policy=model, no teacher wrap, 4B walks the fixture. Host is the judge.
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
    # Hard fixture: oracle is red on the seeded bugs.
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
    os.environ["ETHER_POLICY"] = "model"
    os.environ["ETHER_LIVE_TAKEOVER"] = "0"
    os.environ.setdefault("ETHER_GROK_PRESENT", "1")
    from core.loop.living import FIXTURES

    ws = FIXTURES[name]
    os.environ["ETHER_TOOL_RUNTIME_FIXTURE"] = str(ws)
    from core.pipeline import Pipeline

    result = Pipeline().run(f"Fix the intentional bugs in the {name} fixture. Unaided. policy=model.")
    payload = {
        "name": name,
        "ok": bool(getattr(result, "ok", False) or getattr(result, "success", False)),
        "policy": "model",
        "workspace": str(ws),
        "error": getattr(result, "error", None),
    }
    print(json.dumps(payload, indent=2), flush=True)
    return payload


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("fixture", choices=["lru", "topo", "intervals", "merge", "ledger"])
    p.add_argument("--live", action="store_true")
    args = p.parse_args()
    if args.live:
        out = run_live(args.fixture)
        return 0 if out.get("ok") else 1
    out = seed_is_hard(args.fixture)
    print(json.dumps(out, indent=2), flush=True)
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
