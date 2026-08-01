"""Measure Phase C tool-runtime on repo-oracle fixtures.

Offline (default): scripted decide_fn — proves harness + fixtures, no LLM.
Live: --live uses make_llm_decide_fn() → Rose Quartz / Ollama primary.

Examples:
  python -m scripts.measure_tool_runtime
  python -m scripts.measure_tool_runtime --live --fixture greeter
  python -m scripts.measure_tool_runtime --live --fixture all --json

Does NOT enable ETHER_TOOL_RUNTIME for the whole process unless --wire-env.
Does NOT touch curriculum / bandit / flywheel.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = {
    "greeter": ROOT / "fixtures" / "repo_oracle_toy",
    "wallet": ROOT / "fixtures" / "repo_oracle_wallet",
}

FIXED = {
    "greeter": 'def greet(name: str) -> str:\n    return f"Hello, {name}!"\n',
    "wallet": (
        "class Wallet:\n"
        "    def __init__(self, balance: float = 0.0) -> None:\n"
        "        self.balance = float(balance)\n"
        "    def deposit(self, amount: float) -> float:\n"
        "        if amount < 0:\n"
        "            raise ValueError('amount must be non-negative')\n"
        "        self.balance = self.balance + amount\n"
        "        return self.balance\n"
        "    def withdraw(self, amount: float) -> float:\n"
        "        if amount < 0:\n"
        "            raise ValueError('amount must be non-negative')\n"
        "        if amount > self.balance:\n"
        "            raise ValueError('insufficient funds')\n"
        "        self.balance = self.balance - amount\n"
        "        return self.balance\n"
    ),
}

PRIMARY = {
    "greeter": "greeter.py",
    "wallet": "wallet.py",
}


def _scripted_decide(name: str):
    path = PRIMARY[name]
    body = FIXED[name]
    plan = [
        {"tool": "list_files", "args": {}},
        {"tool": "read_file", "args": {"path": path}},
        {"tool": "write_file", "args": {"path": path, "content": body}},
        {"tool": "run_tests", "args": {}},
    ]
    it = iter(plan)

    def decide(_messages):
        try:
            return next(it)
        except StopIteration:
            return {"tool": "done", "args": {"reason": "exhausted"}}

    return decide


def measure_one(
    name: str,
    *,
    live: bool,
    max_steps: int,
    timeout_s: float,
) -> Dict[str, Any]:
    from core.tool_runtime import ToolRuntime, make_llm_decide_fn

    fixture = FIXTURES[name]
    if not fixture.is_dir():
        return {"fixture": name, "ok": False, "error": f"missing fixture {fixture}"}

    if live:
        decide = make_llm_decide_fn(temperature=0.1, max_tokens=512)
        mode = "live"
    else:
        decide = _scripted_decide(name)
        mode = "scripted"

    t0 = time.perf_counter()
    rt = ToolRuntime(
        fixture_root=fixture,
        decide_fn=decide,
        max_steps=max_steps,
        timeout_s=timeout_s,
        pytest_timeout=30,
    )
    result = rt.run(f"Fix {name} so project tests pass. Use tools.")
    elapsed = time.perf_counter() - t0
    tools = [s.tool for s in result.steps]
    return {
        "fixture": name,
        "mode": mode,
        "ok": bool(result.ok),
        "score": float(result.score),
        "n_steps": int(result.n_steps),
        "elapsed_s": round(elapsed, 3),
        "reason": result.reason or result.error or "",
        "tools": tools,
        "model": os.getenv("ETHER_PRIMARY_MODEL", "") if live else "",
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Measure Phase C tool-runtime")
    ap.add_argument(
        "--fixture",
        choices=["greeter", "wallet", "all"],
        default="all",
    )
    ap.add_argument(
        "--live",
        action="store_true",
        help="Use Rose Quartz / Ollama primary (real model)",
    )
    ap.add_argument("--max-steps", type=int, default=8)
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    names = list(FIXTURES) if args.fixture == "all" else [args.fixture]
    rows: List[Dict[str, Any]] = []
    for name in names:
        rows.append(
            measure_one(
                name,
                live=args.live,
                max_steps=args.max_steps,
                timeout_s=args.timeout,
            )
        )

    if args.json:
        print(json.dumps({"results": rows}, indent=2))
    else:
        for r in rows:
            status = "PASS" if r.get("ok") else "FAIL"
            print(
                f"[{status}] {r['fixture']:8} mode={r.get('mode')} "
                f"score={r.get('score')} steps={r.get('n_steps')} "
                f"elapsed={r.get('elapsed_s')}s tools={r.get('tools')} "
                f"{r.get('reason', '')}"
            )
        n_ok = sum(1 for r in rows if r.get("ok"))
        print(f"summary: {n_ok}/{len(rows)} passed")

    return 0 if all(r.get("ok") for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
