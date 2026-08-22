"""Phase D batch — arms x fixtures in one run.

Arms:
  direct   — ToolRuntime only (Phase C path)
  pipeline — Pipeline + ETHER_TOOL_RUNTIME=1 (Phase D slice 1)
  bare     — Pipeline with tool runtime OFF (generate-only control)

2026-08-14 FastTrack:
- pipeline mode=scripted uses ToolRuntime scripted path (final scoreboard).
- pipeline scripted multi-fixture runs in ThreadPoolExecutor like direct
  (safe: no shared model, isolated staging workspaces).

2026-08-22 OVERHAUL:
- Every fixture ALWAYS produces a countable row (ok or typed failure).
- Exceptions and timeouts write failure_type rows so eligible_rates can see them.
- Sentinel is replaced as soon as the first fixture finishes or fails.
- No more empty scoreboards after host kills the process mid-run.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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


def _fail_row(
    name: str,
    arm: str,
    *,
    live: bool,
    error: str,
    failure_type: str,
    elapsed_s: float = 0.0,
    model: str = "",
) -> Dict[str, Any]:
    """Countable failure row — never leave the scoreboard empty."""
    return {
        "fixture": name,
        "arm": arm,
        "ok": False,
        "score": 0.0,
        "mode": "live" if live else "scripted",
        "error": error[:400],
        "failure_type": failure_type,
        "elapsed_s": round(elapsed_s, 3),
        "n_steps": 0,
        "model": model or os.environ.get("ETHER_PRIMARY_MODEL", ""),
        "honest_tool_path": False,
    }


def _run_direct(name: str, live: bool, max_steps: int, timeout: float) -> Dict[str, Any]:
    t0 = time.perf_counter()
    model = os.environ.get("ETHER_PRIMARY_MODEL", "")
    try:
        from scripts.measure_tool_runtime import measure_one

        r = measure_one(name, live=live, max_steps=max_steps, timeout_s=timeout)
        r["arm"] = "direct"
        if not r.get("ok") and not r.get("failure_type"):
            reason = str(r.get("reason") or r.get("error") or "").lower()
            if "timeout" in reason:
                r["failure_type"] = "timeout"
            elif "no_progress" in reason:
                r["failure_type"] = "no_progress"
            else:
                r["failure_type"] = "live_fail" if live else "scripted_fail"
        return r
    except Exception as e:
        return _fail_row(
            name,
            "direct",
            live=live,
            error=f"{type(e).__name__}: {e}",
            failure_type="exception",
            elapsed_s=time.perf_counter() - t0,
            model=model,
        )


def _run_pipeline(
    name: str, live: bool, max_steps: int, timeout: float, *, bare: bool
) -> Dict[str, Any]:
    fixture = FIXTURES[name]
    model = os.environ.get("ETHER_PRIMARY_MODEL", "")

    if not live and not bare:
        from scripts.measure_tool_runtime import measure_one

        r = measure_one(name, live=False, max_steps=max_steps, timeout_s=timeout)
        r["arm"] = "pipeline"
        r["strategy"] = "tool_runtime_scripted"
        r["mode"] = "scripted"
        return r

    if bare:
        os.environ["ETHER_TOOL_RUNTIME"] = "0"
        os.environ.pop("ETHER_TOOL_RUNTIME_FIXTURE", None)
        arm = "bare"
    else:
        os.environ["ETHER_TOOL_RUNTIME"] = "1"
        os.environ["ETHER_TOOL_RUNTIME_FIXTURE"] = str(fixture.resolve())
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
        row = {
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
            "model": model,
        }
        if live and not bare:
            try:
                from core.loop.handlers.tool_runtime_gate import is_honest_tool_path_pass

                if row.get("ok") and not is_honest_tool_path_pass(row):
                    row["ok"] = False
                    row["honest_tool_path"] = False
                    row.setdefault("degraded", []).append("honest_tool_path_reject")
                else:
                    row["honest_tool_path"] = bool(row.get("ok"))
            except Exception:
                row["honest_tool_path"] = None
        if not row.get("ok"):
            row["failure_type"] = "live_fail" if live else "scripted_fail"
        return row
    except Exception as e:
        return _fail_row(
            name,
            arm,
            live=live,
            error=f"{type(e).__name__}: {e}",
            failure_type="exception",
            elapsed_s=time.perf_counter() - t0,
            model=model,
        )


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
    note: str = "",
) -> None:
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
            "note": note,
        },
        "matrix": {
            n: {a: bool(by.get(n, {}).get(a, {}).get("ok")) for a in arms}
            for n in names
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
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
    ap.add_argument("--max-steps", type=int, default=12)
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

    model = (os.environ.get("ETHER_PRIMARY_MODEL") or "").strip() or "(unset)"
    print(
        f"config: model={model} max_steps={args.max_steps} timeout={args.timeout} jobs={args.jobs}",
        flush=True,
    )

    rows: List[Dict[str, Any]] = []
    sb = Path(args.scoreboard)

    def _persist(note: str = "", partial: bool = True) -> None:
        try:
            _write_scoreboard(
                sb,
                rows,
                mode=args.mode,
                arms=arms,
                model=model,
                max_steps=args.max_steps,
                names=names,
                partial=partial,
                note=note,
            )
        except Exception as e:
            print(f"scoreboard write failed: {type(e).__name__}: {e}", flush=True)

    # Initial sentinel — will be replaced as soon as first fixture completes
    _persist(note="sentinel_on_entry", partial=True)
    print(f"sentinel scoreboard written: {sb}", flush=True)

    try:
        for arm in arms:
            print(f"\n=== arm={arm} mode={args.mode} fixtures={names} ===", flush=True)
            use_pool = (
                not live
                and arm in ("direct", "pipeline")
                and args.jobs > 1
                and len(names) > 1
            )
            if use_pool:
                with ThreadPoolExecutor(max_workers=args.jobs) as ex:
                    if arm == "direct":
                        futs = {
                            ex.submit(
                                _run_direct, n, False, args.max_steps, args.timeout
                            ): n
                            for n in names
                        }
                    else:
                        futs = {
                            ex.submit(
                                _run_pipeline,
                                n,
                                False,
                                args.max_steps,
                                args.timeout,
                                bare=False,
                            ): n
                            for n in names
                        }
                    for fut in as_completed(futs):
                        try:
                            r = fut.result()
                        except Exception as e:
                            n = futs[fut]
                            r = _fail_row(
                                n,
                                arm,
                                live=False,
                                error=f"{type(e).__name__}: {e}",
                                failure_type="exception",
                                model=model,
                            )
                        rows.append(r)
                        st = "PASS" if r.get("ok") else "FAIL"
                        print(
                            f"[{st}] {r.get('fixture'):10} arm={arm} score={r.get('score')} "
                            f"steps={r.get('n_steps')} elapsed={r.get('elapsed_s')}s "
                            f"ft={r.get('failure_type', '')}",
                            flush=True,
                        )
                        _persist(note="partial", partial=True)
                continue

            for name in names:
                t0 = time.perf_counter()
                try:
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
                except Exception as e:
                    traceback.print_exc()
                    r = _fail_row(
                        name,
                        arm,
                        live=live,
                        error=f"{type(e).__name__}: {e}",
                        failure_type="exception",
                        elapsed_s=time.perf_counter() - t0,
                        model=model,
                    )
                rows.append(r)
                st = "PASS" if r.get("ok") else "FAIL"
                extra = (
                    r.get("strategy")
                    or r.get("error")
                    or r.get("reason")
                    or r.get("failure_type")
                    or ""
                )
                print(
                    f"[{st}] {name:10} arm={arm:8} score={r.get('score')} "
                    f"elapsed={r.get('elapsed_s')}s {extra}",
                    flush=True,
                )
                _persist(note="partial", partial=True)

        print("\n=== summary matrix ===", flush=True)
        by: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            by.setdefault(r.get("fixture"), {})[r.get("arm")] = r
        print(
            f"{'fixture':10} "
            + " ".join(f"{a:10}" for a in ("direct", "pipeline", "bare")),
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
        return 0 if n_ok == len(rows) and rows else 1
    finally:
        # If we still have zero rows (killed before first fixture), write
        # explicit timeout rows so eligible_rates can see the attempt.
        if not rows:
            for name in names:
                for arm in arms:
                    rows.append(
                        _fail_row(
                            name,
                            arm,
                            live=live,
                            error="process killed before fixture completed (external timeout)",
                            failure_type="timeout",
                            model=model,
                        )
                    )
            print(
                f"FORCE-WROTE {len(rows)} timeout rows (empty results on exit)",
                flush=True,
            )
        _persist(note="final", partial=False)
        print(f"scoreboard: {sb} rows={len(rows)}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
