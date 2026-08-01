"""Measure Phase C tool-runtime on repo-oracle fixtures.

Tiers:
  easy  — greeter, wallet
  hard  — lru, merge, ledger, topo, intervals
  all   — easy + hard

  python -m scripts.measure_tool_runtime --tier hard --jobs 4
  python -m scripts.measure_tool_runtime --live --tier hard
  python -m scripts.batch_measure --live
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = {
    "greeter": ROOT / "fixtures" / "repo_oracle_toy",
    "wallet": ROOT / "fixtures" / "repo_oracle_wallet",
    "lru": ROOT / "fixtures" / "repo_oracle_lru",
    "merge": ROOT / "fixtures" / "repo_oracle_merge",
    "ledger": ROOT / "fixtures" / "repo_oracle_ledger",
    "topo": ROOT / "fixtures" / "repo_oracle_topo",
    "intervals": ROOT / "fixtures" / "repo_oracle_intervals",
}

EASY = ("greeter", "wallet")
HARD = ("lru", "merge", "ledger", "topo", "intervals")

SOLUTIONS = ROOT / "fixtures" / "_fixed_solutions"

_EASY_FIXED = {
    "greeter": {
        "greeter.py": 'def greet(name: str) -> str:\n    return f"Hello, {name}!"\n',
    },
    "wallet": {
        "wallet.py": (
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
    },
}


def _fixed_files(name: str) -> Dict[str, str]:
    if name in _EASY_FIXED:
        return dict(_EASY_FIXED[name])
    sol_dir = SOLUTIONS / name
    if not sol_dir.is_dir():
        raise FileNotFoundError(f"no fixed solutions for {name} at {sol_dir}")
    out: Dict[str, str] = {}
    for p in sorted(sol_dir.glob("*.py")):
        out[p.name] = p.read_text(encoding="utf-8")
    return out


def _scripted_decide(name: str):
    files = _fixed_files(name)
    plan: List[Dict[str, Any]] = [{"tool": "list_files", "args": {}}]
    for path in files:
        plan.append({"tool": "read_file", "args": {"path": path}})
    for path, body in files.items():
        plan.append({"tool": "write_file", "args": {"path": path, "content": body}})
    plan.append({"tool": "run_tests", "args": {}})
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
        decide = make_llm_decide_fn(temperature=0.1, max_tokens=1024)
        mode = "live"
        steps = max(max_steps, 12)
    else:
        decide = _scripted_decide(name)
        mode = "scripted"
        steps = max_steps

    t0 = time.perf_counter()
    rt = ToolRuntime(
        fixture_root=fixture,
        decide_fn=decide,
        max_steps=steps,
        timeout_s=timeout_s,
        pytest_timeout=45,
    )
    result = rt.run(
        f"Fix the {name} package so all project tests pass. "
        f"Read the tests and source, edit the broken file(s), then run_tests."
    )
    elapsed = time.perf_counter() - t0
    return {
        "fixture": name,
        "tier": "hard" if name in HARD else "easy",
        "mode": mode,
        "ok": bool(result.ok),
        "score": float(result.score),
        "n_steps": int(result.n_steps),
        "elapsed_s": round(elapsed, 3),
        "reason": result.reason or result.error or "",
        "tools": [s.tool for s in result.steps],
        "model": os.getenv("ETHER_PRIMARY_MODEL", "") if live else "",
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Measure Phase C tool-runtime")
    ap.add_argument(
        "--tier",
        choices=["easy", "hard", "all"],
        default="easy",
        help="easy=greeter+wallet, hard=lru+merge+ledger+topo+intervals",
    )
    ap.add_argument(
        "--fixture",
        choices=list(FIXTURES) + ["all"],
        default=None,
    )
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--max-steps", type=int, default=10)
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--jobs", type=int, default=4, help="parallel workers for scripted only")
    ap.add_argument("--scoreboard", type=str, default="", help="write JSON results path")
    args = ap.parse_args(argv)

    if args.fixture and args.fixture != "all":
        names = [args.fixture]
    elif args.fixture == "all" or args.tier == "all":
        names = list(EASY) + list(HARD)
    elif args.tier == "hard":
        names = list(HARD)
    else:
        names = list(EASY)

    def _run(name: str) -> Dict[str, Any]:
        return measure_one(
            name,
            live=args.live,
            max_steps=args.max_steps,
            timeout_s=args.timeout,
        )

    rows: List[Dict[str, Any]] = []
    if (not args.live) and args.jobs > 1 and len(names) > 1:
        with ThreadPoolExecutor(max_workers=args.jobs) as ex:
            futs = {ex.submit(_run, n): n for n in names}
            done = {}
            for fut in as_completed(futs):
                r = fut.result()
                done[r["fixture"]] = r
                status = "PASS" if r.get("ok") else "FAIL"
                print(
                    f"[{status}] {r['fixture']:10} tier={r.get('tier')} mode={r.get('mode')} "
                    f"score={r.get('score')} steps={r.get('n_steps')} "
                    f"elapsed={r.get('elapsed_s')}s",
                    flush=True,
                )
            rows = [done[n] for n in names if n in done]
    else:
        for name in names:
            r = _run(name)
            rows.append(r)
            status = "PASS" if r.get("ok") else "FAIL"
            print(
                f"[{status}] {r['fixture']:10} tier={r.get('tier')} mode={r.get('mode')} "
                f"score={r.get('score')} steps={r.get('n_steps')} "
                f"elapsed={r.get('elapsed_s')}s tools={r.get('tools')} "
                f"{r.get('reason', '')}",
                flush=True,
            )

    n_ok = sum(1 for r in rows if r.get("ok"))
    print(f"summary: {n_ok}/{len(rows)} passed", flush=True)

    if args.scoreboard:
        sb = Path(args.scoreboard)
        payload = {
            "results": rows,
            "summary": {"passed": n_ok, "total": len(rows), "live": bool(args.live)},
        }
        sb.parent.mkdir(parents=True, exist_ok=True)
        sb.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"scoreboard: {sb}", flush=True)

    if args.json:
        print(json.dumps({"results": rows}, indent=2))

    return 0 if all(r.get("ok") for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
