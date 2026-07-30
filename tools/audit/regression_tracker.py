#!/usr/bin/env python3
"""P3 regression tracker: classify run records vs the findings baseline,
update baseline statuses, aggregate trends, emit preventive suggestions.

Usage:
    python tools/audit/regression_tracker.py --violations out.jsonl
        [--baseline tools/audit/findings_baseline.json]
        [--events state/regression_events.jsonl]
        [--trend-out state/trend.json] [--update-baseline]
        [--commit <sha>]

Classification per P3 §2: true_regression / pattern_migration /
new_violation / still_open / suppressed. CI gate policy (P3 §7): exit 1
only on new blocker-class violations and true regressions of fixed
blocker/high findings.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.audit import DEFAULT_BASELINE
from tools.audit.fingerprint import (NEW_VIOLATION, PATTERN_MIGRATION,
                                     STILL_OPEN, SUPPRESSED, TRUE_REGRESSION,
                                     classify, score_event)
from tools.audit.ingest import ingest

GATE_FAIL_CLASSES = {TRUE_REGRESSION}
EVENT_WEIGHT = {NEW_VIOLATION: 1.0, PATTERN_MIGRATION: 1.5,
                TRUE_REGRESSION: 2.0}

# Preventive-suggestion prescriptions keyed by rule (P3 §6)
PRESCRIPTIONS = {
    "QUAL-002": "adopt the degraded-vector pattern repo-wide (degraded: "
                "List[str] on PipelineResult; precedent pipeline.py:676-690)",
    "STATE-002": "migrate the module's state writes to the queue_lock + "
                 "atomic-replace helper (core/batch_queue.py:19-52)",
    "STATE-001": "migrate the module's state writes to the queue_lock + "
                 "atomic-replace helper (core/batch_queue.py:19-52)",
    "ARCH-001": "invert the dependency through core/schemas.py and a "
                "composition root (A-4)",
    "QUAL-006": "extract a shared strip_markdown_fences helper; canonical "
                "implementation is core/agent_loop.py (F9)",
}


def iso_week(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        dt = datetime.now(timezone.utc)
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def atomic_append(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(text)


def classify_run(rows: list, baseline: dict, commit: str,
                 ts: str) -> dict:
    """Classify every ingested row; returns events + summary buckets."""
    rule_status = baseline.get("rule_status", {})
    events = []
    buckets = {TRUE_REGRESSION: [], PATTERN_MIGRATION: [], NEW_VIOLATION: [],
               STILL_OPEN: [], SUPPRESSED: []}
    for row in rows:
        if row.get("suppressed"):
            buckets[SUPPRESSED].append(row)
            continue
        cls = classify(row, baseline)
        ev = {
            "ts": ts,
            "commit": commit or row.get("commit", ""),
            "event": cls,
            "rule_id": row["rule_id"],
            "category": row.get("category", ""),
            "severity": row.get("severity", "warn"),
            "pattern_hash": row.get("pattern_hash", ""),
            "fingerprint": row.get("fingerprint", ""),
            "module": row.get("module", ""),
            "context": row.get("context", ""),
            "file": row.get("file", ""),
            "line": row.get("line", 0),
            "finding_ids": row.get("finding_ids", []),
            "message": row.get("message", ""),
        }
        ev["score"] = score_event(
            cls, ev["severity"],
            rule_in_review=rule_status.get(ev["rule_id"]) == "review")
        events.append(ev)
        buckets[cls].append(ev)
    # resolved: baseline open violation *sites* absent from this run.
    # Fingerprints are pattern-only (P3), so site identity adds
    # module+context — a pattern that survives elsewhere is not resolved.
    seen_sites = {(r.get("fingerprint"), r.get("module"), r.get("context"))
                  for r in rows}
    resolved = [v for v in baseline.get("violations", [])
                if v.get("status", "open") == "open"
                and (v.get("fingerprint"), v.get("module"), v.get("context"))
                not in seen_sites]
    return {"events": events, "buckets": buckets, "resolved": resolved}


def update_baseline(baseline: dict, classified: dict, ts: str) -> dict:
    """Baseline RMW (status transitions as PR suggestions — a human merges).

    - new_violation rows enter as status 'open'
    - resolved rows are marked 'fixed_pending_review' (never auto-verified:
      the flywheel may never forgive its own regressions — D-01 lesson)
    """
    known = {v.get("fingerprint") for v in baseline.get("violations", [])}
    for ev in classified["buckets"][NEW_VIOLATION]:
        if ev["fingerprint"] in known:
            continue
        baseline.setdefault("violations", []).append({
            "rule_id": ev["rule_id"],
            "fingerprint": ev["fingerprint"],
            "pattern_hash": ev["pattern_hash"],
            "module": ev["module"],
            "context": ev["context"],
            "file": ev["file"],
            "line": ev["line"],
            "status": "open",
            "finding_ids": ev["finding_ids"],
            "first_seen": ts,
        })
        known.add(ev["fingerprint"])
    resolved_fps = {v.get("fingerprint") for v in classified["resolved"]}
    for v in baseline.get("violations", []):
        if v.get("fingerprint") in resolved_fps:
            v["status"] = "fixed_pending_review"
    return baseline


def rebuild_trend(events_path: Path, rows_now: list) -> dict:
    """Materialized aggregates (P3 §5) — rebuilt by the job, never on read."""
    events = []
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    per_rule_week: dict = defaultdict(int)
    cat_week: dict = defaultdict(int)
    module_weight: dict = defaultdict(float)
    rule_weight: dict = defaultdict(float)
    for ev in events:
        week = iso_week(ev.get("ts", ""))
        if ev.get("event") in EVENT_WEIGHT:
            per_rule_week[f"{ev.get('rule_id','?')}|{week}"] += 1
            cat_week[f"{ev.get('category','?')}|{week}"] += 1
            module_weight[ev.get("module", "?")] += \
                EVENT_WEIGHT.get(ev["event"], 1.0)
            rule_weight[ev.get("rule_id", "?")] += \
                EVENT_WEIGHT.get(ev["event"], 1.0)
    top_modules = sorted(module_weight.items(), key=lambda kv: -kv[1])[:5]
    return {
        "generated": datetime.now(timezone.utc).isoformat(),
        "events_total": len(events),
        "regressions_per_rule_per_week": dict(sorted(per_rule_week.items())),
        "category_heat": dict(sorted(cat_week.items())),
        "top_recidivist_modules": [{"module": m, "score": round(s, 1)}
                                   for m, s in top_modules],
        "rule_recidivism": {k: round(v, 1) for k, v in
                            sorted(rule_weight.items(), key=lambda kv: -kv[1])},
        "fp_rate_per_rule": {},  # maintained by fp_feedback.py
    }


def suggestions(events: list, trend: dict) -> list:
    """Preventive-suggestion engine (P3 §6 thresholds)."""
    out = []
    now = datetime.now(timezone.utc)
    recent = []
    for ev in events:
        try:
            ts = datetime.fromisoformat(ev.get("ts", "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if (now - ts).days <= 30 and ev.get("event") in EVENT_WEIGHT:
            recent.append(ev)
    # 1. rule regressed >= 3 times in 30 days -> structural refactor
    by_rule = Counter(ev["rule_id"] for ev in recent)
    for rid, n in by_rule.most_common():
        if n >= 3:
            out.append({
                "kind": "structural_refactor",
                "rule_id": rid,
                "evidence": f"{n} regression-class events in 30 days",
                "suggestion": PRESCRIPTIONS.get(
                    rid, "schedule a structural fix; the rule keeps "
                         "re-regressing"),
            })
    # 2. top-2 recidivist modules -> ownership/review pairing
    for entry in trend.get("top_recidivist_modules", [])[:2]:
        out.append({
            "kind": "review_pairing",
            "module": entry["module"],
            "evidence": f"recidivism score {entry['score']} (top-2, 30d)",
            "suggestion": "require human co-review for bot commits touching "
                          "this module (mitigates B2/S-04 unreviewed-push)",
        })
    # 3. same pattern in >= 2 modules in 30d -> extract shared helper
    by_pattern: dict = defaultdict(set)
    for ev in recent:
        if ev.get("event") == PATTERN_MIGRATION:
            by_pattern[(ev["rule_id"], ev.get("pattern_hash"))].add(
                ev.get("module"))
    for (rid, ph), mods in by_pattern.items():
        if len(mods) >= 2:
            out.append({
                "kind": "extract_shared_helper",
                "rule_id": rid,
                "pattern_hash": ph,
                "evidence": f"pattern migrated across {sorted(mods)} in 30d",
                "suggestion": PRESCRIPTIONS.get(
                    rid, "extract a shared helper; the pattern is migrating"),
            })
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="P3 regression tracker")
    ap.add_argument("--violations", required=True, help="runner JSONL")
    ap.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    ap.add_argument("--events",
                    default=str(Path(__file__).parent.parent.parent
                                / "state" / "regression_events.jsonl"))
    ap.add_argument("--trend-out",
                    default=str(Path(__file__).parent.parent.parent
                                / "state" / "trend.json"))
    ap.add_argument("--commit", default="")
    ap.add_argument("--update-baseline", action="store_true",
                    help="write status transitions back to the baseline file")
    ap.add_argument("--json", action="store_true", help="machine-readable out")
    args = ap.parse_args(argv)

    baseline_path = Path(args.baseline)
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        baseline = {}
    rows, errors, _dropped = ingest(Path(args.violations))
    for e in errors:
        print(f"warn: {e}", file=sys.stderr)

    ts = datetime.now(timezone.utc).isoformat()
    classified = classify_run(rows, baseline, args.commit, ts)
    events_path = Path(args.events)
    if classified["events"]:
        atomic_append(events_path, "".join(
            json.dumps(ev, sort_keys=True) + "\n"
            for ev in classified["events"]))

    trend = rebuild_trend(events_path, rows)
    trend_path = Path(args.trend_out)
    trend_path.parent.mkdir(parents=True, exist_ok=True)
    trend_path.write_text(json.dumps(trend, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")

    if args.update_baseline:
        baseline = update_baseline(baseline, classified, ts)
        tmp = baseline_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
        tmp.replace(baseline_path)

    all_events = []
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            try:
                all_events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    sug = suggestions(all_events, trend)

    b = classified["buckets"]
    summary = {
        "true_regressions": b[TRUE_REGRESSION],
        "pattern_migrations": b[PATTERN_MIGRATION],
        "new_violations": b[NEW_VIOLATION],
        "still_open": b[STILL_OPEN],
        "suppressed": b[SUPPRESSED],
        "resolved": classified["resolved"],
        "preventive_suggestions": sug,
        "counts": {k: len(v) for k, v in b.items()} | {
            "resolved": len(classified["resolved"])},
    }
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(f"regression scan: {len(rows)} records vs baseline")
        for label, key in (("true_regressions", TRUE_REGRESSION),
                           ("pattern_migrations", PATTERN_MIGRATION),
                           ("new_violations", NEW_VIOLATION),
                           ("still_open", STILL_OPEN),
                           ("suppressed", SUPPRESSED),
                           ("resolved", "resolved")):
            print(f"  {label:<20} {summary['counts'][key]}")
        for ev in b[TRUE_REGRESSION] + b[PATTERN_MIGRATION]:
            print(f"  [{ev['event']}] {ev['rule_id']} {ev['file']}:{ev['line']}"
                  f" score={ev['score']} ({ev['module']}::{ev['context']})")
        for s in sug:
            print(f"  [suggestion:{s['kind']}] {s.get('rule_id') or s.get('module')}"
                  f" — {s['suggestion']}")

    # CI gate policy (P3 §7): fail only on true regressions of fixed
    # blocker/high findings and new blocker-class violations.
    hard = [ev for ev in b[TRUE_REGRESSION]
            if ev["severity"] in ("blocker", "high")]
    hard += [ev for ev in b[NEW_VIOLATION] if ev["severity"] == "blocker"]
    if hard:
        print(f"GATE: {len(hard)} gate-failing regression event(s) — exit 1")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
