#!/usr/bin/env python3
"""P3 false-positive feedback loop (§8).

Usage:
    # mark a false positive: insert the in-code marker AND denylist the
    # pattern hash (suppression attaches to the pattern, not the line)
    python tools/audit/fp_feedback.py RULE-ID PATTERN_HASH "reason"
        [--file path --line N] [--baseline findings_baseline.json]

    # recompute per-rule FP rates from the event log; >20% -> rule "review"
    python tools/audit/fp_feedback.py --recompute [--events ...] [--trend ...]

Effects:
- inserts `# audit-fp: RULE-ID reason` above --line in --file (optional)
- appends {rule_id, pattern_hash, reason, added_by, date} to the baseline
  fp_denylist (atomic write, tmp+replace)
- a pattern FP'd >= 2 times under the same rule becomes a rule-level
  exclusion candidate (reported)
- per-rule FP rate > 20% -> rule_status[rule] = "review" (score x0.5,
  alerts downgraded) — recorded in the baseline, shown on the leaderboard
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.audit import DEFAULT_BASELINE, FP_RE

FP_REVIEW_THRESHOLD = 0.20
EXCLUSION_THRESHOLD = 2


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def insert_marker(file: Path, line: int, rule_id: str, reason: str) -> bool:
    """Insert `# audit-fp: RULE-ID reason` above the given line."""
    try:
        lines = file.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        print(f"error: cannot read {file}: {e}", file=sys.stderr)
        return False
    idx = max(0, min(line - 1, len(lines)))
    indent = ""
    if idx < len(lines):
        indent = lines[idx][: len(lines[idx]) - len(lines[idx].lstrip())]
    lines.insert(idx, f"{indent}# audit-fp: {rule_id} {reason}")
    atomic_write(file, "\n".join(lines) + "\n")
    return True


def add_denylist(baseline_path: Path, rule_id: str, pattern_hash: str,
                 reason: str) -> dict:
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        baseline = {"schema_version": 1, "violations": [], "fp_denylist": []}
    deny = baseline.setdefault("fp_denylist", [])
    if not any(d.get("rule_id") == rule_id
               and d.get("pattern_hash") == pattern_hash for d in deny):
        deny.append({
            "rule_id": rule_id,
            "pattern_hash": pattern_hash,
            "reason": reason,
            "added_by": getpass.getuser(),
            "date": datetime.now(timezone.utc).date().isoformat(),
        })
    atomic_write(baseline_path,
                 json.dumps(baseline, indent=2, sort_keys=True) + "\n")
    return baseline


def recompute_fp_rates(events_path: Path, baseline_path: Path,
                       trend_path: Path) -> dict:
    """Per-rule FP rate over the event log; >20% -> rule 'review'."""
    events = []
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    total = Counter(ev.get("rule_id") for ev in events)
    fps = Counter(ev.get("rule_id") for ev in events
                  if ev.get("event") in ("suppressed", "fp"))
    rates = {rid: round(fps[rid] / n, 3)
             for rid, n in total.items() if n}
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        baseline = {}
    status = baseline.setdefault("rule_status", {})
    leaderboard = []
    for rid, rate in sorted(rates.items(), key=lambda kv: -kv[1]):
        if rate > FP_REVIEW_THRESHOLD:
            status[rid] = "review"
            leaderboard.append({"rule_id": rid, "fp_rate": rate})
        elif status.get(rid) == "review":
            status.pop(rid)  # recovered below threshold
    # pattern-level exclusions: same pattern FP'd >= 2 times under one rule
    deny = baseline.get("fp_denylist", [])
    pat_count = Counter((d.get("rule_id"), d.get("pattern_hash")) for d in deny)
    exclusions = [{"rule_id": rid, "pattern_hash": ph, "times": n}
                  for (rid, ph), n in pat_count.items()
                  if n >= EXCLUSION_THRESHOLD]
    if trend_path.exists():
        try:
            trend = json.loads(trend_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            trend = {}
    else:
        trend = {}
    trend["fp_rate_per_rule"] = rates
    trend["fp_leaderboard"] = leaderboard
    trend["pattern_exclusions"] = exclusions
    atomic_write(trend_path, json.dumps(trend, indent=2, sort_keys=True) + "\n")
    atomic_write(baseline_path,
                 json.dumps(baseline, indent=2, sort_keys=True) + "\n")
    return {"fp_rate_per_rule": rates, "fp_leaderboard": leaderboard,
            "pattern_exclusions": exclusions}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="P3 false-positive feedback")
    ap.add_argument("rule_id", nargs="?", help="e.g. QUAL-002")
    ap.add_argument("pattern_hash", nargs="?")
    ap.add_argument("reason", nargs="?",
                    help="e.g. 'intentional: subprocess probe in test'")
    ap.add_argument("--file", help="source file for the in-code marker")
    ap.add_argument("--line", type=int, default=0)
    ap.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    ap.add_argument("--recompute", action="store_true")
    ap.add_argument("--events",
                    default=str(Path(__file__).parent.parent.parent
                                / "state" / "regression_events.jsonl"))
    ap.add_argument("--trend",
                    default=str(Path(__file__).parent.parent.parent
                                / "state" / "trend.json"))
    args = ap.parse_args(argv)

    if args.recompute:
        out = recompute_fp_rates(Path(args.events), Path(args.baseline),
                                 Path(args.trend))
        print(json.dumps(out, indent=2, sort_keys=True))
        if out["fp_leaderboard"]:
            print("rules entering REVIEW state (FP rate > 20%): alerts "
                  "downgrade to warn, score x0.5")
        return 0

    if not (args.rule_id and args.pattern_hash and args.reason):
        ap.error("rule_id, pattern_hash and reason are required "
                 "(or use --recompute)")
    if args.file and args.line:
        if insert_marker(Path(args.file), args.line, args.rule_id,
                         args.reason):
            print(f"inserted `# audit-fp: {args.rule_id} {args.reason}` "
                  f"above {args.file}:{args.line}")
    else:
        print(f"add this marker on the offending line:\n"
              f"  # audit-fp: {args.rule_id} {args.reason}")
    baseline = add_denylist(Path(args.baseline), args.rule_id,
                            args.pattern_hash, args.reason)
    print(f"denylist now {len(baseline.get('fp_denylist', []))} entr(ies); "
          "suppression attaches to the pattern hash and survives refactoring")
    # update FP rates after recording
    out = recompute_fp_rates(Path(args.events), Path(args.baseline),
                             Path(args.trend))
    rate = out["fp_rate_per_rule"].get(args.rule_id)
    if rate is not None:
        print(f"{args.rule_id} FP rate: {rate:.1%}"
              + (" — RULE ENTERS REVIEW" if rate > FP_REVIEW_THRESHOLD else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
