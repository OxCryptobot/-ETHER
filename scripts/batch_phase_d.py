"""Phase D batch — arms x fixtures in one run.

Arms:
  direct   — ToolRuntime only (Phase C path)
  pipeline — Pipeline + ETHER_TOOL_RUNTIME=1 (Phase D slice 1)
  bare     — Pipeline with tool runtime OFF (generate-only control)

  python -m scripts.batch_phase_d --arm direct --mode scripted --tier hard
  python -m scripts.batch_phase_d --arm pipeline --mode live --fixture ledger --max-steps 16 --timeout 500

2026-08-14: scoreboard is now written after every fixture and in a finally
block so a mid-run timeout/kill still leaves a usable partial artifact.
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

# Critical: CLI loads .env; batch must too or Rose Quartz falls back to 3b.
try:
    from core.dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

HARD = ("lru", "merge", "ledger", "topo", "intervals")
EASY = ("greeter", "wallet")
ALL = EASY + HARD

FIXTURES = {
    "greeter": ROOT / "fixtures" / "repo_oracle_toy",
    "wallet": ROOT / "fixtures" / "repo_oracle_wallet",
    "lru": ROOT / "fixtures" / "repo_oracle_lru",
    "merge": ROOT / "fixtures" / "repo_oracle_merge",
    "ledger": ROOT / "fixtures" / "repo_oracle_ledger",
    "topo": ROOT / "fixtures" / "repo_oracle_topo",
    "intervals": ROOT / "fixtures" / "repo_oracle_intervals",
}


def _run_direct(name: str, live: bool, max_steps: int, timeout: float) -> Dict[str, Any]:
    from scripts.measure_tool_runtime import measure_one

    r = measure_one(name, live=live, max_steps=max_steps, timeout_s=timeout)
    r["arm"] = "direct"
    return r


def _run_pipeline(
    name: str, live: bool, max_steps: int, timeout: float, *, bare: bool
) -> Dict[str, Any]:
    fixture = FIXTURES[name]
    if bare:
        os.environ["ETHER_TOOL_RUNTIME"] = "0"
        os.environ.pop("ETHER_TOOL_RUNTIME_FIXTURE", None)
        arm = "bare"
    else:
        os.environ["ETHER_TOOL_RUNTIME"] = "1"
        os.environ["ETHER_TOOL_RUNTIME_FIXTURE"] = str(fixture.resolve())
        # Honor --max-steps exactly (do not clamp over a higher user budget).
        os.environ["ETHER_TOOL_RUNTIME_STEPS"] = str(int(max_steps))
        os.environ["ETHER_TOOL_RUNTIME_SECONDS"] = str(int(timeout))
        arm = "pipeline"

    objective = (
        f"Fix the {name} package so all project tests pass. "
        f"Read tests and source, apply fixes, verify with tests."
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
                    "detail": str(getattr(s, "detail", ""))[:120],
                }
            )
        return {
            "fixture": name,
            "arm": arm,
            "ok": ok,
            "score": score,
            "strategy": strategy,
            "status": status,
            "repo_oracle_ok": repo_ok,
            "elapsed_s": round(elapsed, 3),
            "mode": "live" if live else "scripted",
            "stages": stages,
            "degraded": list(getattr(result, "degraded", []) or [])[:6],
            "model": os.environ.get("ETHER_PRIMARY_MODEL", ""),
        }
    except Exception as e:
        return {
            "fixture": name,
            "arm": arm,
            "ok": False,
            "score": 0.0,
            "error": f"{type(e).__name__}: {e}"[:300],
            "elapsed_s": round(time.perf_counter() - t0, 3),
            "mode": "live" if live else "scripted",
            "model": os.environ.get("ETHER_PRIMARY_MODEL", ""),
        }


def _write_scoreboard(
    path: Path,
    rows: List[Dict[str, Any]],
    *,
    mode: str,
    arms: List[str],
    model: str,
    max_steps: int,
    names: List[str],
    partial: bool = False,
) -> None:
    """Always-safe scoreboard dump. Called after every fixture and in finally."""
    by: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        by.setdefault(r.get("fixture"), {})[r.get("arm")] = r
    n_ok = sum(1 for r in rows if r.get("ok"))
    payload = {
        "results": rows,
        "summary": {
            "passed": n_ok,
            "total": len(rows),
            "mode": mode,
            "arms": arms,
            "model": model,
            "max_steps": max_steps,
            "partial": partial,
        },
        "matrix": {
            n: {a: bool(by.get(n, {}).get(a, {}).get("ok")) for a in arms}
            for n in names
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic-ish write: temp then replace so a kill mid-write cannot leave
    # a truncated JSON that later readers treat as valid.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Phase D batch measure")
    ap.add_argument(
        "--arm", choices=["direct", "pipeline", "bare", "all"], default="all"
    )
    ap.add_argument("--mode", choices=["scripted", "live"], default="scripted")
    ap.add_argument("--tier", choices=["easy", "hard", "all"], default="hard")
    ap.add_argument("--fixture", default=None)
    ap.add_argument("--timeout", type=float, default=400.0)
    ap.add_argument(
        "--max-steps",
        type=int,
        default=12,
        help="Tool-runtime step budget (pipeline sets ETHER_TOOL_RUNTIME_STEPS)",
    )
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument(
        "--scoreboard", type=str, default="artifacts/scoreboard_phase_d.json"
    )
    args = ap.parse_args(argv)

    live = args.mode == "live"
    if args.fixture:
        names = [args.fixture]
    elif args.tier == "easy":
        names = list(EASY)
    elif args.tier == "all":
        names = list(ALL)
    else:
        names = list(HARD)

    if args.arm == "all":
        arms = ["direct", "pipeline"] if live else ["direct"]
        if live:
            arms.append("bare")
    else:
        arms = [args.arm]

    model = (os.environ.get("ETHER_PRIMARY_MODEL") or "").strip() or "(unset → rose default 3b)"
    print(
        f"config: model={model} max_steps={args.max_steps} timeout={args.timeout}",
        flush=True,
    )

    rows: List[Dict[str, Any]] = []
    sb = Path(args.scoreboard)

    try:
        for arm in arms:
            print(f"\n=== arm={arm} mode={args.mode} fixtures={names} ===", flush=True)
            if arm == "direct" and not live and args.jobs > 1 and len(names) > 1:
                with ThreadPoolExecutor(max_workers=args.jobs) as ex:
                    futs = {
                        ex.submit(_run_direct, n, False, args.max_steps, args.timeout): n
                        for n in names
                    }
                    for fut in as_completed(futs):
                        r = fut.result()
                        rows.append(r)
                        st = "PASS" if r.get("ok") else "FAIL"
                        print(
                            f"[{st}] {r.get('fixture'):10} arm=direct score={r.get('score')} "
                            f"steps={r.get('n_steps')} elapsed={r.get('elapsed_s')}s",
                            flush=True,
                        )
                        # Incremental dump so a later kill still leaves data.
                        _write_scoreboard(
                            sb, rows, mode=args.mode, arms=arms, model=model,
                            max_steps=args.max_steps, names=names, partial=True,
                        )
                continue

            for name in names:
                if arm == "direct":
                    r = _run_direct(name, live, args.max_steps, args.timeout)
                elif arm == "pipeline":
                    r = _run_pipeline(
                        name, live, args.max_steps, args.timeout, bare=False
                    )
                else:
                    r = _run_pipeline(
                        name, live, args.max_steps, args.timeout, bare=True
                    )
                rows.append(r)
                st = "PASS" if r.get("ok") else "FAIL"
                extra = r.get("strategy") or r.get("error") or r.get("reason") or ""
                print(
                    f"[{st}] {name:10} arm={arm:8} score={r.get('score')} "
                    f"elapsed={r.get('elapsed_s')}s repo_ok={r.get('repo_oracle_ok')} {extra}",
                    flush=True,
                )
                if not r.get("ok"):
                    for s in r.get("stages") or []:
                        print(
                            f"  stage={s.get('stage')} ok={s.get('success')} {s.get('detail')}",
                            flush=True,
                        )
                # Write after every fixture. A host timeout now leaves a partial
                # but usable scoreboard instead of nothing.
                _write_scoreboard(
                    sb, rows, mode=args.mode, arms=arms, model=model,
                    max_steps=args.max_steps, names=names, partial=True,
                )

        print("\n=== summary matrix ===", flush=True)
        by: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            by.setdefault(r.get("fixture"), {})[r.get("arm")] = r
        print(
            f"{'fixture':10} " + " ".join(f"{a:10}" for a in ("direct", "pipeline", "bare")),
            flush=True,
        )
        blank = "--"
        for name in names:
            cells = []
            for a in ("direct", "pipeline", "bare"):
                r = by.get(name, {}).get(a)
                if not r:
                    cells.append(f"{blank:10}")
                else:
                    mark = "PASS" if r.get("ok") else "FAIL"
                    cells.append(f"{mark:10}")
            print(f"{name:10} " + " ".join(cells), flush=True)

        n_ok = sum(1 for r in rows if r.get("ok"))
        print(f"\nsummary: {n_ok}/{len(rows)} passed", flush=True)
        return 0 if n_ok == len(rows) else 1
    finally:
        # Final authoritative write (partial=False). Guarantees an artifact
        # even if the process is about to be killed by the job runner.
        try:
            _write_scoreboard(
                sb, rows, mode=args.mode, arms=arms, model=model,
                max_steps=args.max_steps, names=names, partial=False,
            )
            print(f"scoreboard: {sb}", flush=True)
        except Exception as e:
            print(f"scoreboard write failed: {type(e).__name__}: {e}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
