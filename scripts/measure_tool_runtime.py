"""Measure Phase C tool-runtime on repo-oracle fixtures.

  python -m scripts.measure_tool_runtime --live --fixture ledger
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

OBJECTIVES = {
    "greeter": (
        "Fix greeter.py so ALL tests pass. list_files, read tests, read greeter.py, "
        "write_file the Hello fix, run_tests, done. JSON only."
    ),
    "wallet": (
        "Fix wallet.py so ALL tests pass. list_files, read tests, read wallet.py, "
        "write_file deposit/withdraw fix, run_tests, done. JSON only."
    ),
    "topo": (
        "Fix topo_sort so ALL tests pass. Cycles MUST raise ValueError. Kahn indegree. "
        "Then run_tests."
    ),
    "ledger": (
        "Fix ledger.py. account.py is CORRECT. After at most one list_files and one "
        "read_file, you MUST mutate: anchor_edit debit+credit, replace_once return s+s "
        "with return s, then run_tests. No more read_file."
    ),
    "merge": (
        "Fix merge.py. After at most one list_files and one read_file you MUST mutate: "
        "replace_once return list(b), replace_once return list(a), anchor_edit extend b "
        "remainder, then run_tests. No more read_file."
    ),
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
        try:
            from core.model_select import ensure_model_env

            chosen = ensure_model_env()
            os.environ["ETHER_PRIMARY_MODEL"] = chosen
        except Exception:
            pass
        if name in EASY:
            steps = min(max(max_steps, 6), 8)
            max_tok = 384
        else:
            steps = max(max_steps, 10)
            max_tok = 768
        decide = make_llm_decide_fn(temperature=0.0, max_tokens=max_tok)
        policy = "model"
        try:
            from core.hard_live_playbook import wrap_live_decide

            decide = wrap_live_decide(name, decide)
            policy = "model"
        except Exception:
            pass
        mode = "live"
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
        pytest_timeout=30 if name in EASY else 45,
    )
    obj = OBJECTIVES.get(
        name,
        f"Fix the {name} package so all project tests pass. "
        f"Read the tests and source, edit the broken file(s), then run_tests.",
    )
    result = rt.run(obj)
    elapsed = time.perf_counter() - t0
    row = {
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
        "policy": "scripted",
    }
    if live:
        tagged = "model"
        try:
            tagged = str(decide.policy())  # type: ignore[attr-defined]
        except Exception:
            tagged = "model"
        reason = str(row.get("reason") or "")
        if tagged == "craft_helper" or reason in {"craft_helper"}:
            tagged = "craft_helper"
        elif reason.startswith("playbook_") or tagged == "teacher_playbook":
            tagged = "teacher_playbook"
        row["policy"] = tagged

    if not row["ok"]:
        reason = str(row.get("reason") or "").lower()
        if "timeout" in reason:
            row["failure_type"] = "timeout"
        elif "no_progress" in reason:
            row["failure_type"] = "no_progress"
        else:
            row["failure_type"] = "live_fail" if live else "scripted_fail"
    return row


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Measure Phase C tool-runtime")
    ap.add_argument("--tier", choices=["easy", "hard", "all"], default="easy")
    ap.add_argument("--fixture", choices=list(FIXTURES) + ["all"], default=None)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--max-steps", type=int, default=10)
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--scoreboard", type=str, default="")
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
            name, live=args.live, max_steps=args.max_steps, timeout_s=args.timeout
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
