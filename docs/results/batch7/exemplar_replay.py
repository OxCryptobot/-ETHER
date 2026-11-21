"""Batch 7 offline replay of ETHER_EXEMPLARS on the real goal seed (config/goal_seed.json, 60 goals).

No model, no writes to the repo. Every goal gets a stand-in "kept" diff of its own target (a one-line
change inside the real function, so the diff carries real context lines incl. the `def` line). Then:
  A. leave-one-out (library = the other 59): coverage, leak exclusions, prompt chars, budget fit,
     spoiler-guard trips, same-file share.
  B. growth: random order, each goal kept with p=0.2 (about the host's guessed keep rate); coverage of
     the NEXT goal as the library grows (10 seeds).
Run: python docs/results/batch7/exemplar_replay.py  -> exemplar_replay.json next to it.
"""
from __future__ import annotations

import json
import os
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
os.environ["ETHER_EXEMPLARS"] = "1"

from core.agent import exemplars as ex  # noqa: E402
from core.agent import goal_source as gs  # noqa: E402
from core.agent.goal_quality import check  # noqa: E402
from core.kernel.context_budget import context_char_budget  # noqa: E402


def stand_in(goal):
    text = (ROOT / goal["file"]).read_text(encoding="utf-8", errors="ignore") if (ROOT / goal["file"]).is_file() else ""
    before = ex._func_text(text, goal["symbol"])
    if not before:
        before = f"def {goal['symbol'].split('.')[-1]}():\n    pass"
    lines = before.splitlines()
    i = 1 if len(lines) > 1 else 0
    after = "\n".join(lines[: i + 1] + [lines[i][: len(lines[i]) - len(lines[i].lstrip())] + "pass  # kept edit"] + lines[i + 1:])
    return {"id": goal["id"], "kind": goal.get("kind"), "file": goal["file"], "symbol": goal["symbol"],
            "nodeid": goal.get("nodeid"), "error_kind": goal.get("error_kind"), "error": str(goal.get("error") or "")[-200:],
            "span": bool(goal.get("span")), "tokens": ex._goal_tokens(goal), "diff": ex.diff_of(before, after),
            "kept": True, "ts": goal["id"]}


def main():
    seed = json.loads((ROOT / "config/goal_seed.json").read_text(encoding="utf-8"))
    goals = list(seed["goals"].values())
    lib = [stand_in(g) for g in goals]
    out = {"goals": len(goals), "ctx": {}}
    for ctx in ("4096", "8192"):
        os.environ["ETHER_MODEL_CTX"] = ctx
        budget = context_char_budget()
        cov = leaks = spoil = base_spoil = over = same_file = shown = ctx_cut = 0
        added, scores = [], []
        for g in goals:
            leaks += sum(1 for r in lib if ex.leaks(g, r))
            got = ex.retrieve(ROOT, g, k=1, rows=lib)
            if not got:
                continue
            cov += 1
            scores.append(got[0]["score"])
            same_file += int(got[0]["file"] == g["file"])
            try:
                base = gs.build_prompt(ROOT, g)
                p = gs.build_prompt(ROOT, g, ex.behaviour(), exemplar=got)
            except Exception:
                continue
            added.append(len(p) - len(base) if gs.EXEMPLAR_HEAD in p else 0)
            shown += int(gs.EXEMPLAR_HEAD in p)
            code_base = base.split(f"{g['file']} (current):", 1)[-1].rsplit("Reply with", 1)[0].strip()
            ctx_cut += int(bool(code_base) and code_base[-400:] not in p)
            over += int(len(p) > budget)
            cur = (ROOT / g["file"]).read_text(encoding="utf-8", errors="ignore") if (ROOT / g["file"]).is_file() else ""
            was = "spoiler" in check(g, base, cur)["reasons"]
            base_spoil += int(was)
            spoil += int("spoiler" in check(g, p, cur)["reasons"] and not was)
        out["ctx"][ctx] = {"budget_chars": budget, "coverage_loo": round(cov / len(goals), 3), "covered": cov,
                           "leak_exclusions": leaks, "spoiler_trips_added_by_exemplar": spoil,
                           "spoiler_trips_already_in_base_prompt": base_spoil, "over_budget": over, "hint_shown": shown, "code_context_cut_by_hint": ctx_cut,
                           "same_file_share": round(same_file / cov, 3) if cov else None,
                           "score_median": round(statistics.median(scores), 3) if scores else None,
                           "block_chars_median": int(statistics.median(added)) if added else 0,
                           "block_chars_max": max(added) if added else 0}
    os.environ["ETHER_MODEL_CTX"] = "4096"
    curve = {}
    for s in range(10):
        rng = random.Random(s)
        order = goals[:]
        rng.shuffle(order)
        kept = []
        for g in order:
            n = len(kept)
            hit = bool(ex.retrieve(ROOT, g, k=1, rows=kept))
            curve.setdefault(n, []).append(hit)
            if rng.random() < 0.2:
                kept.append(stand_in(g))
    out["growth_p_keep_0.2"] = {str(n): round(sum(v) / len(v), 3) for n, v in sorted(curve.items()) if len(v) >= 5}
    (Path(__file__).parent / "exemplar_replay.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
