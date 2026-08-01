"""Phase D slice 1 — measure pipeline path with ETHER_TOOL_RUNTIME=1.

  python -m scripts.measure_pipeline_tool --fixture ledger --path pipeline --live
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
    "lru": ROOT / "fixtures" / "repo_oracle_lru",
    "merge": ROOT / "fixtures" / "repo_oracle_merge",
    "ledger": ROOT / "fixtures" / "repo_oracle_ledger",
    "topo": ROOT / "fixtures" / "repo_oracle_topo",
    "intervals": ROOT / "fixtures" / "repo_oracle_intervals",
}
HARD = ("lru", "merge", "ledger", "topo", "intervals")
EASY = ("greeter", "wallet")


def _measure_tool_direct(name: str, live: bool, max_steps: int, timeout_s: float) -> Dict[str, Any]:
    from scripts.measure_tool_runtime import measure_one

    return measure_one(name, live=live, max_steps=max_steps, timeout_s=timeout_s)


def _measure_pipeline(name: str, live: bool, max_steps: int, timeout_s: float) -> Dict[str, Any]:
    fixture = FIXTURES[name]
    if not fixture.is_dir():
        return {"fixture": name, "path": "pipeline", "ok": False, "error": "missing fixture"}

    os.environ["ETHER_TOOL_RUNTIME"] = "1"
    os.environ["ETHER_TOOL_RUNTIME_FIXTURE"] = str(fixture)
    os.environ["ETHER_TOOL_RUNTIME_STEPS"] = str(max(max_steps, 12) if live else max_steps)
    os.environ["ETHER_TOOL_RUNTIME_SECONDS"] = str(int(timeout_s))

    objective = (
        f"Fix the {name} package so all project tests pass. "
        f"Use tools: read tests and source, write fixes, run_tests."
    )

    t0 = time.perf_counter()
    try:
        from core.pipeline import Pipeline

        result = Pipeline().run(objective)
        elapsed = time.perf_counter() - t0
        strategy = str(getattr(result, "strategy", "") or "")
        status = str(getattr(result, "status", "") or "")
        repo_ok = getattr(result, "repo_oracle_ok", None)
        score = float(
            getattr(result, "verification_score", 0)
            or getattr(result, "execution_score", 0)
            or 0.0
        )
        # Honest pass: full score or explicit repo oracle ok.
        # status=="complete" alone is NOT success (Phase D false PASS at 0.25).
        if repo_ok is True:
            ok = True
            score = max(score, 1.0)
        elif repo_ok is False:
            ok = False
        else:
            ok = score >= 0.999 and status.lower() in (
                "ok",
                "success",
                "passed",
                "complete",
                "completed",
            )
        stages = []
        for s in list(getattr(result, "stages", None) or [])[:12]:
            stages.append(
                {
                    "stage": getattr(s, "stage", ""),
                    "success": getattr(s, "success", None),
                    "detail": str(getattr(s, "detail", ""))[:160],
                }
            )
        return {
            "fixture": name,
            "path": "pipeline",
            "ok": ok,
            "score": score,
            "strategy": strategy,
            "status": status,
            "repo_oracle_ok": repo_ok,
            "elapsed_s": round(elapsed, 3),
            "live": live,
            "degraded": list(getattr(result, "degraded", []) or [])[:8],
            "stages": stages,
            "env_tool": os.environ.get("ETHER_TOOL_RUNTIME", ""),
            "env_fixture": os.environ.get("ETHER_TOOL_RUNTIME_FIXTURE", "")[-80:],
        }
    except Exception as e:
        return {
            "fixture": name,
            "path": "pipeline",
            "ok": False,
            "error": f"{type(e).__name__}: {e}"[:300],
            "elapsed_s": round(time.perf_counter() - t0, 3),
            "live": live,
        }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Phase D: pipeline tool-runtime measure")
    ap.add_argument("--tier", choices=["easy", "hard", "all"], default=None)
    ap.add_argument("--fixture", choices=list(FIXTURES) + ["all"], default=None)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--max-steps", type=int, default=12)
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--path", choices=["direct", "pipeline", "both"], default="both")
    ap.add_argument("--scoreboard", type=str, default="")
    args = ap.parse_args(argv)

    if args.fixture and args.fixture != "all":
        names = [args.fixture]
    elif args.fixture == "all" or args.tier == "all":
        names = list(EASY) + list(HARD)
    elif args.tier == "hard":
        names = list(HARD)
    elif args.tier == "easy":
        names = list(EASY)
    else:
        names = ["ledger"]

    rows: List[Dict[str, Any]] = []
    for name in names:
        if args.path in ("direct", "both"):
            r = _measure_tool_direct(name, args.live, args.max_steps, args.timeout)
            r["path"] = "direct"
            rows.append(r)
            st = "PASS" if r.get("ok") else "FAIL"
            print(
                f"[{st}] {name:10} path=direct  score={r.get('score')} "
                f"steps={r.get('n_steps')} elapsed={r.get('elapsed_s')}s "
                f"{r.get('reason', r.get('error', ''))}",
                flush=True,
            )
        if args.path in ("pipeline", "both"):
            r = _measure_pipeline(name, args.live, args.max_steps, args.timeout)
            rows.append(r)
            st = "PASS" if r.get("ok") else "FAIL"
            print(
                f"[{st}] {name:10} path=pipeline score={r.get('score')} "
                f"strategy={r.get('strategy')} elapsed={r.get('elapsed_s')}s "
                f"repo_ok={r.get('repo_oracle_ok')} {r.get('error', '')}",
                flush=True,
            )
            for s in r.get("stages") or []:
                print(
                    f"  stage={s.get('stage')} ok={s.get('success')} {s.get('detail')}",
                    flush=True,
                )
            if r.get("degraded"):
                print(f"  degraded={r.get('degraded')}", flush=True)

    n_ok = sum(1 for r in rows if r.get("ok"))
    print(f"summary: {n_ok}/{len(rows)} passed", flush=True)
    if args.scoreboard:
        sb = Path(args.scoreboard)
        sb.parent.mkdir(parents=True, exist_ok=True)
        sb.write_text(
            json.dumps({"results": rows, "passed": n_ok, "total": len(rows)}, indent=2),
            encoding="utf-8",
        )
        print(f"scoreboard: {sb}", flush=True)
    return 0 if n_ok == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
