#!/usr/bin/env python3
"""Verify hooks + ledger import; soft-patch guidance for pipeline."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.pipeline_hooks import bandit_context, prepare_code_for_sandbox
from core.ledger import compute_ledger
from core.learning import BanditPolicy


def main() -> int:
    ctx = bandit_context("refactor module file", tier=2, fail_kind="SyntaxError")
    b = BanditPolicy()
    s = b.select(context=ctx)
    code, meta = prepare_code_for_sandbox(
        "def is_even(n):\n    return n % 2 == 0\n", objective="is_even"
    )
    led = compute_ledger()
    print(
        json.dumps(
            {
                "strategy": s,
                "ctx": ctx,
                "synth": meta.get("synth"),
                "ledger_runs": led.get("runs_sampled"),
                "avg_run_ms": led.get("avg_run_ms"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
