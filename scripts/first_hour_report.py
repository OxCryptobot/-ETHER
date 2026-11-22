#!/usr/bin/env python3
"""First-hour report after a push: is the host learning? Read-only.

    python scripts/first_hour_report.py [--ref origin/main] [--since "1 hour ago"] [--fetch] [--json]
    python scripts/first_hour_report.py --local          # read the working tree instead of a ref

Reads artifacts/host_main.json and artifacts/learning_summary.json at <ref> (git show, no
checkout) plus `git log <ref> --since`, and prints:
  host:      tick time, health / selfcheck_error / plan_error, next goal, sota note, queue depth
  learning:  graded / kept, kept per attempt, revert rate, regressions caught, spoiler share
  by kind:   attempts / passes per goal kind (recent rows) and per via (metrics.by_via)
  arms:      per kind: pulls, passes, posterior mean per arm; arm spread (entropy, top share)
  commits:   commits/h in the window, split host_main / other, and by author
An old-schema summary (pre-batch-2 host code: {"day", "goals"}) is reported as such.
Never writes, never pushes; --fetch runs `git fetch origin` only.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]


def git(*args: str, root: Path = ROOT) -> str:
    r = subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True, timeout=120)
    return r.stdout if r.returncode == 0 else ""


def read_artifact(name: str, ref: Optional[str], root: Path = ROOT) -> Optional[Dict[str, Any]]:
    try:
        text = (root / "artifacts" / name).read_text(encoding="utf-8") if ref is None else \
            git("show", f"{ref}:artifacts/{name}", root=root)
        return json.loads(text) if text.strip() else None
    except Exception:
        return None


def _entropy(counts: List[int]) -> float:
    n = sum(counts)
    if n <= 0:
        return 0.0
    return round(-sum(c / n * math.log2(c / n) for c in counts if c), 3)


def host_view(hm: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not hm:
        return {"present": False}
    sota = hm.get("sota") if isinstance(hm.get("sota"), dict) else {}
    return {"present": True, "ts": hm.get("ts"), "health": hm.get("health", "n/a (pre-batch-5 host)"),
            "selfcheck_error": hm.get("selfcheck_error"), "plan_error": hm.get("plan_error"),
            "next_goal": hm.get("next_goal"), "seed_depth": hm.get("seed_depth"),
            "sota_note": sota.get("note"), "sota_ok": sota.get("ok"), "kept_n": sota.get("kept_n"),
            "real_queue": hm.get("real_queue")}


def learning_view(ls: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not ls:
        return {"present": False}
    if "totals" not in ls:
        return {"present": True, "schema": "old", "note": "pre-batch-2 summary (host still on old code)",
                "day": ls.get("day"), "goals": len(ls.get("goals") or [])}
    m = ls.get("metrics") or {}
    t = ls.get("totals") or {}
    by_kind: Dict[str, Dict[str, int]] = {}
    for r in ls.get("recent") or []:
        k = str(r.get("goal_kind") or "legacy")
        cell = by_kind.setdefault(k, {"attempts": 0, "passes": 0})
        cell["attempts"] += 1
        cell["passes"] += int(r.get("kind") == "pass" or bool(r.get("tests_ok")))
    arms: Dict[str, Any] = {}
    bandit = ls.get("bandit") or {}
    for kind, buckets in bandit.items():
        if not isinstance(buckets, dict) or kind in ("algo", "arms", "gamma", "cost_aware", "factored"):
            continue
        pulls: Counter = Counter()
        passes: Counter = Counter()
        means: Dict[str, float] = {}
        for _bucket, row in buckets.items():
            for arm, c in ((row or {}).get("arms") or {}).items():
                pulls[arm] += int(c.get("n", 0))
                passes[arm] += int(c.get("passes", 0))
                means[arm] = c.get("post_mean")
        n = sum(pulls.values())
        arms[kind] = {"pulls": dict(pulls), "passes": dict(passes), "post_mean": means,
                      "entropy_bits": _entropy(list(pulls.values())),
                      "arms_used": sum(1 for v in pulls.values() if v),
                      "top_share": round(max(pulls.values()) / n, 3) if n else None}
    return {"present": True, "schema": ls.get("schema"), "generated": ls.get("generated"),
            "graded": t.get("graded"), "real_graded": t.get("real_graded"), "real_passes": t.get("real_passes"),
            "kept": m.get("kept"), "attempts": m.get("attempts"), "kept_per_attempt": m.get("kept_per_attempt"),
            "revert_rate": m.get("revert_rate"), "regressions_caught": m.get("regressions_caught"),
            "spoiler_share": t.get("spoiler_share"), "filler_rate": m.get("filler_rate"),
            "tool_edits": m.get("tool_edits"), "by_via": m.get("by_via") or {}, "by_kind_recent": by_kind,
            "arms": arms, "promoted": ls.get("promoted"), "real_queue": ls.get("real_queue"),
            "exemplars": ls.get("exemplars"), "dup_share": m.get("dup_share"), "by_temp": m.get("by_temp") or {}}


def commits_view(ref: Optional[str], since: str, root: Path = ROOT) -> Dict[str, Any]:
    out = git("log", ref or "HEAD", f"--since={since}", "--format=%ct\t%an\t%s", root=root)
    rows = [ln.split("\t", 2) for ln in out.splitlines() if ln.count("\t") >= 2]
    if not rows:
        return {"n": 0, "per_hour": 0.0}
    ts = sorted(int(r[0]) for r in rows)
    now = datetime.now(timezone.utc).timestamp()
    span_h = max(1 / 60, (now - ts[0]) / 3600.0)
    host = sum(1 for r in rows if r[2].startswith("1650 host_main"))
    return {"n": len(rows), "window_h": round(span_h, 2), "per_hour": round(len(rows) / span_h, 1),
            "host_main": host, "other": len(rows) - host, "by_author": dict(Counter(r[1] for r in rows).most_common(5)),
            "last": datetime.fromtimestamp(ts[-1], timezone.utc).isoformat()}


def report(ref: Optional[str], since: str, root: Path = ROOT) -> Dict[str, Any]:
    return {"ref": ref or "(working tree)", "head": (git("log", "-1", "--format=%h %cI %s", ref or "HEAD", root=root)
                                                     or "").strip(),
            "host": host_view(read_artifact("host_main.json", ref, root)),
            "learning": learning_view(read_artifact("learning_summary.json", ref, root)),
            "commits": commits_view(ref, since, root)}


def _fmt(v: Any) -> str:
    return "-" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))


def render(doc: Dict[str, Any]) -> str:
    h, ls, c = doc["host"], doc["learning"], doc["commits"]
    out = [f"ETHER first-hour report  ref={doc['ref']}  head={doc['head']}"]
    if h.get("present"):
        out.append(f"host: tick {h['ts']}  health={h['health']}  selfcheck_error={_fmt(h['selfcheck_error'])}  "
                   f"plan_error={_fmt(h['plan_error'])}")
        out.append(f"      next_goal={_fmt(h['next_goal'])}  sota={_fmt(h['sota_note'])} kept_n={_fmt(h['kept_n'])}  "
                   f"seed_depth={_fmt(h['seed_depth'])}")
    else:
        out.append("host: host_main.json missing")
    if not ls.get("present"):
        out.append("learning: learning_summary.json missing")
    elif ls.get("schema") == "old":
        out.append(f"learning: OLD schema ({ls['note']}; day {ls['day']}, {ls['goals']} goal names)")
    else:
        out.append(f"learning: graded={_fmt(ls['graded'])} real={_fmt(ls['real_graded'])}/{_fmt(ls['real_passes'])} pass  "
                   f"kept/attempt={_fmt(ls['kept_per_attempt'])} ({_fmt(ls['kept'])}/{_fmt(ls['attempts'])})  "
                   f"revert_rate={_fmt(ls['revert_rate'])}  regressions_caught={_fmt(ls['regressions_caught'])}  "
                   f"spoiler={_fmt(ls['spoiler_share'])}  tool_edits={_fmt(ls['tool_edits'])}")
        if ls["by_kind_recent"]:
            out.append("  pass by goal kind (recent): " + ", ".join(
                f"{k} {v['passes']}/{v['attempts']}" for k, v in sorted(ls["by_kind_recent"].items())))
        if ls["by_via"]:
            out.append("  kept by via: " + ", ".join(
                f"{k} {v.get('kept', 0)}/{v.get('attempts', 0)}" for k, v in sorted(ls["by_via"].items())))
        for kind, a in sorted(ls["arms"].items()):
            arms = ", ".join(f"{arm} {a['passes'].get(arm, 0)}/{n} (mu {_fmt(a['post_mean'].get(arm))})"
                             for arm, n in sorted(a["pulls"].items(), key=lambda kv: -kv[1]))
            out.append(f"  arms[{kind}]: used {a['arms_used']}  entropy {a['entropy_bits']} bits  "
                       f"top share {_fmt(a['top_share'])}  | {arms}")
        if ls.get("dup_share") is not None or ls.get("by_temp"):  # batch 8
            out.append(f"  duplicate replies {_fmt(ls.get('dup_share'))}  kept by temperature: " + (", ".join(
                f"T={k} {v.get('kept', 0)}/{v.get('attempts', 0)}" for k, v in sorted((ls.get('by_temp') or {}).items()))
                or "-"))
        ex = ls.get("exemplars") or {}
        if ex and "error" not in ex:  # batch 7 (ETHER_EXEMPLARS=record|1)
            out.append(f"  exemplars[{_fmt(ex.get('mode'))}]: library {_fmt(ex.get('library'))}  shown {_fmt(ex.get('shown'))}  "
                       f"kept/attempt shown {_fmt(ex.get('kept_per_attempt_shown'))} vs other "
                       f"{_fmt(ex.get('kept_per_attempt_other'))}  reuse {_fmt(ex.get('reuse_rate'))}")
    out.append(f"commits: {c['n']} in {_fmt(c.get('window_h'))} h = {c['per_hour']}/h  "
               f"(host_main {c.get('host_main', 0)}, other {c.get('other', 0)})  authors {c.get('by_author', {})}")
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ref", default="origin/main")
    ap.add_argument("--local", action="store_true", help="read the working tree, not a ref")
    ap.add_argument("--since", default="1 hour ago")
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--root", default=str(ROOT))
    a = ap.parse_args(argv)
    root = Path(a.root)
    if a.fetch:
        git("fetch", "-q", "origin", root=root)
    doc = report(None if a.local else a.ref, a.since, root)
    print(json.dumps(doc, indent=1, default=str) if a.json else render(doc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
