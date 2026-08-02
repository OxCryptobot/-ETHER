"""Phase F — mutation restore WITH unified diff in the objective (git-style signal).

  python -m scripts.batch_phase_f --arm direct --mode scripted
  python -m scripts.batch_phase_f --arm direct --mode live --max-steps 16 --timeout 500
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from core.dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

MUTATIONS: List[Dict[str, str]] = [
    {
        "id": "ledger_no_debit",
        "fixture": "ledger",
        "file": "ledger.py",
        "old": "        a.debit(amount)\n        b.credit(amount)",
        "new": "        # mutated: credit only\n        b.credit(amount)",
    },
    {
        "id": "ledger_double_total",
        "fixture": "ledger",
        "file": "ledger.py",
        "old": "        return sum(a.balance for a in self._accounts.values())",
        "new": "        s = sum(a.balance for a in self._accounts.values())\n        return s + s",
    },
    {
        "id": "topo_drop_cycle_raise",
        "fixture": "topo",
        "file": "topo.py",
        "old": '    if len(out) != len(nodes):\n        raise ValueError("cycle detected")\n    return out',
        "new": "    # mutated: silent partial order on cycles\n    return out",
    },
    {
        "id": "lru_no_evict",
        "fixture": "lru",
        "file": "lru.py",
        "old": "        if len(self._data) > self.capacity:\n            self._data.popitem(last=False)",
        "new": "        # mutated: never evict\n        pass",
    },
    {
        "id": "merge_drop_b_tail",
        "fixture": "merge",
        "file": "merge.py",
        "old": "    if i < len(a):\n        out.extend(a[i:])\n    if j < len(b):\n        out.extend(b[j:])\n    return out",
        "new": "    if i < len(a):\n        out.extend(a[i:])\n    # mutated: drop remainder of b\n    return out",
    },
    {
        "id": "intervals_no_sort",
        "fixture": "intervals",
        "file": "intervals.py",
        "old": "    sorted_iv = sorted(intervals, key=lambda x: (x[0], x[1]))",
        "new": "    sorted_iv = list(intervals)  # mutated: no sort",
    },
]

FIXTURE_DIRS = {
    "ledger": ROOT / "fixtures" / "repo_oracle_ledger",
    "topo": ROOT / "fixtures" / "repo_oracle_topo",
    "lru": ROOT / "fixtures" / "repo_oracle_lru",
    "merge": ROOT / "fixtures" / "repo_oracle_merge",
    "intervals": ROOT / "fixtures" / "repo_oracle_intervals",
}


def _build_mutated_tree(mut: Dict[str, str]) -> Tuple[Path, str]:
    name = mut["fixture"]
    src = FIXTURE_DIRS[name]
    fixed = ROOT / "fixtures" / "_fixed_solutions" / name
    staging = Path(tempfile.mkdtemp(prefix=f"ether_f_{mut['id']}_"))
    for p in src.rglob("*"):
        if not p.is_file():
            continue
        if any(x in p.parts for x in (".git", "__pycache__", ".pytest_cache")):
            continue
        rel = p.relative_to(src)
        dest = staging / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dest)
    for p in fixed.rglob("*.py"):
        rel = p.relative_to(fixed)
        dest = staging / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")

    target = staging / mut["file"]
    before = target.read_text(encoding="utf-8")
    if mut["old"] not in before:
        shutil.rmtree(staging, ignore_errors=True)
        raise ValueError(f"anchor missing: {mut['id']}")
    after = before.replace(mut["old"], mut["new"], 1)
    target.write_text(after, encoding="utf-8")

    diff = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{mut['file']}",
            tofile=f"b/{mut['file']}",
        )
    )
    (staging / "REGRESSION.diff").write_text(diff, encoding="utf-8")
    return staging, diff


def _run_direct(
    mut: Dict[str, str], live: bool, max_steps: int, timeout: float
) -> Dict[str, Any]:
    from core.tool_runtime import ToolRuntime, make_llm_decide_fn
    from core.repo_oracle import run_project_pytest

    tree, diff = _build_mutated_tree(mut)
    t0 = time.perf_counter()
    try:
        pre = run_project_pytest(tree, test_args=["tests"], timeout=60)
        if pre.get("ok"):
            return {
                "mutation": mut["id"],
                "arm": "direct",
                "ok": False,
                "score": 0.0,
                "error": "mutation_did_not_break_tests",
                "elapsed_s": round(time.perf_counter() - t0, 3),
            }

        if live:
            decide = make_llm_decide_fn()
        else:
            fixed_body = (
                ROOT / "fixtures" / "_fixed_solutions" / mut["fixture"] / mut["file"]
            ).read_text(encoding="utf-8")
            steps_plan = [
                {"tool": "list_files", "args": {}},
                {"tool": "read_file", "args": {"path": "REGRESSION.diff"}},
                {"tool": "read_file", "args": {"path": mut["file"]}},
                {
                    "tool": "write_file",
                    "args": {"path": mut["file"], "content": fixed_body},
                },
                {"tool": "run_tests", "args": {}},
            ]
            idx = {"i": 0}

            def decide(messages, _idx=idx, _plan=steps_plan):
                i = _idx["i"]
                if i >= len(_plan):
                    return {"tool": "done", "args": {"reason": "budget"}}
                _idx["i"] = i + 1
                return _plan[i]

        diff_snip = diff if len(diff) < 2500 else (diff[:2400] + "\n... (truncated)\n")
        objective = (
            f"A regression was introduced in {mut['file']}. "
            f"Unified diff of the bad change:\n```\n{diff_snip}\n```\n"
            f"Also available as REGRESSION.diff in the workspace. "
            f"Restore correct behaviour so all project tests pass."
        )
        rt = ToolRuntime(
            fixture_root=tree,
            decide_fn=decide,
            max_steps=max_steps,
            timeout_s=timeout,
        )
        result = rt.run(objective)
        return {
            "mutation": mut["id"],
            "fixture": mut["fixture"],
            "arm": "direct",
            "ok": bool(result.ok),
            "score": float(result.score),
            "n_steps": result.n_steps,
            "reason": result.reason or result.error,
            "elapsed_s": round(time.perf_counter() - t0, 3),
            "mode": "live" if live else "scripted",
            "diff_chars": len(diff),
        }
    finally:
        shutil.rmtree(tree, ignore_errors=True)


def _run_bare(mut: Dict[str, str], timeout: float) -> Dict[str, Any]:
    tree, diff = _build_mutated_tree(mut)
    t0 = time.perf_counter()
    try:
        os.environ["ETHER_TOOL_RUNTIME"] = "0"
        os.environ.pop("ETHER_TOOL_RUNTIME_FIXTURE", None)
        from core.pipeline import Pipeline

        diff_snip = diff if len(diff) < 2500 else diff[:2400] + "\n..."
        objective = (
            f"A regression was introduced in {mut['file']}. Diff:\n```\n{diff_snip}\n```\n"
            f"Fix the {mut['fixture']} package so all project tests pass."
        )
        result = Pipeline().run(objective)
        score = float(
            getattr(result, "verification_score", 0)
            or getattr(result, "execution_score", 0)
            or 0.0
        )
        repo_ok = getattr(result, "repo_oracle_ok", None)
        ok = repo_ok is True or score >= 0.999
        return {
            "mutation": mut["id"],
            "fixture": mut["fixture"],
            "arm": "bare",
            "ok": bool(ok),
            "score": score,
            "elapsed_s": round(time.perf_counter() - t0, 3),
            "mode": "live",
        }
    except Exception as e:
        return {
            "mutation": mut["id"],
            "arm": "bare",
            "ok": False,
            "score": 0.0,
            "error": f"{type(e).__name__}: {e}"[:300],
            "elapsed_s": round(time.perf_counter() - t0, 3),
        }
    finally:
        shutil.rmtree(tree, ignore_errors=True)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Phase F diff-aware mutation restore")
    ap.add_argument("--arm", choices=["direct", "bare", "all"], default="direct")
    ap.add_argument("--mode", choices=["scripted", "live"], default="scripted")
    ap.add_argument("--mutation", default=None)
    ap.add_argument("--max-steps", type=int, default=16)
    ap.add_argument("--timeout", type=float, default=500.0)
    ap.add_argument("--scoreboard", default="artifacts/scoreboard_phase_f.json")
    args = ap.parse_args(argv)

    muts = MUTATIONS
    if args.mutation:
        muts = [m for m in MUTATIONS if m["id"] == args.mutation]
        if not muts:
            print("unknown mutation", args.mutation)
            return 2

    arms = ["direct", "bare"] if args.arm == "all" else [args.arm]
    if args.mode == "scripted":
        arms = [a for a in arms if a != "bare"]

    model = (os.environ.get("ETHER_PRIMARY_MODEL") or "").strip() or "(unset)"
    print(
        f"config: model={model} max_steps={args.max_steps} mutations={len(muts)} phase=F-diff",
        flush=True,
    )

    rows: List[Dict[str, Any]] = []
    for arm in arms:
        print(f"\n=== arm={arm} mode={args.mode} ===", flush=True)
        for mut in muts:
            if arm == "direct":
                r = _run_direct(
                    mut,
                    live=(args.mode == "live"),
                    max_steps=args.max_steps,
                    timeout=args.timeout,
                )
            else:
                r = _run_bare(mut, timeout=args.timeout)
            rows.append(r)
            st = "PASS" if r.get("ok") else "FAIL"
            print(
                f"[{st}] {mut['id']:24} score={r.get('score')} "
                f"steps={r.get('n_steps')} elapsed={r.get('elapsed_s')}s "
                f"{r.get('reason') or r.get('error') or ''}",
                flush=True,
            )

    n_ok = sum(1 for r in rows if r.get("ok"))
    print(f"\nsummary: {n_ok}/{len(rows)} passed", flush=True)
    print("(Phase E baseline: direct live 3/6, bare live 1/6)", flush=True)
    sb = Path(args.scoreboard)
    sb.parent.mkdir(parents=True, exist_ok=True)
    sb.write_text(
        json.dumps(
            {
                "results": rows,
                "passed": n_ok,
                "total": len(rows),
                "model": model,
                "phase": "F",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"scoreboard: {sb}", flush=True)
    return 0 if n_ok == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
