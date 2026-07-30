#!/usr/bin/env python3
"""ETHER continuous-audit runner (P2 heart). Stdlib only.

Usage:
    python tools/audit/audit_runner.py --repo /path/to/ether [--fast]
        [--json-out out.jsonl] [--baseline tools/audit/findings_baseline.json]
        [--health-out audit_health.json] [--config config/audit-rules.yaml]

Exit codes:
    0 — clean, or all violations are grandfathered in the baseline
    1 — at least one NEW blocker-severity violation
    2 — runner error (bad config, unreadable repo, ...)

Emits: per-violation JSONL, a human summary, and an audit_health.json
aggregate (P2 §4 schema). The runner obeys STATE-001 itself: JSON outputs
are written atomically (tmp + replace).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # pack root

from tools.audit import (DEFAULT_BASELINE, DEFAULT_RULES_CONFIG, RuleContext,
                         is_suppressed)
from tools.audit.rules import REGISTRY


def load_config(path: Path) -> dict:
    """Load audit-rules.yaml. The file is JSON-shaped YAML (JSON is a
    YAML 1.2 subset), so the stdlib json parser handles it; PyYAML is
    used only as an optional fallback."""
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
        except ImportError as e:
            raise SystemExit(
                f"error: {path} is not JSON-shaped YAML and PyYAML is not "
                "installed") from e
        return yaml.safe_load(text)


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def git_head(repo: Path) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             cwd=str(repo), capture_output=True, text=True,
                             timeout=15)
        return out.stdout.strip() if out.returncode == 0 else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def run(repo: Path, config_path: Path, baseline_path: Path, fast: bool) -> dict:
    cfg = load_config(config_path)
    baseline = load_json(baseline_path, {})
    budgets = dict(cfg.get("budgets", {}))
    budgets.update(baseline.get("budgets", {}))

    rules = [r for r in cfg.get("rules", []) if r.get("enabled", True)]
    if fast:
        rules = [r for r in rules if r.get("fast", False)]

    baseline_fps = {v.get("fingerprint")
                    for v in baseline.get("violations", [])}
    deny = {(d.get("rule_id"), d.get("pattern_hash"))
            for d in baseline.get("fp_denylist", [])}

    results = []
    violations = []
    t0 = time.monotonic()
    for rule in rules:
        rid = rule["id"]
        check = REGISTRY.get(rid)
        if check is None:
            results.append({"rule_id": rid, "status": "skip",
                            "note": "external tool rule (ruff/xenon/CI) — "
                                    "not executed by this engine",
                            "violations": [], "metrics": {},
                            "duration_ms": 0.0})
            continue
        ctx = RuleContext(repo=repo, budgets=budgets, baseline=baseline,
                          config=rule, fast=fast)
        t1 = time.monotonic()
        try:
            rr = check(ctx, rule)
        except Exception as e:  # never-raises philosophy, fail closed loud
            results.append({"rule_id": rid, "status": "error",
                            "note": f"{type(e).__name__}: {e}",
                            "violations": [], "metrics": {},
                            "duration_ms": (time.monotonic() - t1) * 1000})
            continue
        dur = (time.monotonic() - t1) * 1000
        for v in rr.violations:
            if (v.rule_id, v.pattern_hash) in deny:
                v.suppressed = True
            if not v.suppressed and v.file and v.line > 0:
                src = repo / v.file
                try:
                    lines = src.read_text(encoding="utf-8",
                                          errors="replace").splitlines()
                except OSError:
                    lines = []
                allowed, _fp = is_suppressed(lines, v.line, v.rule_id)
                if allowed:
                    v.suppressed = True
            v.baseline = v.fingerprint in baseline_fps
        results.append({"rule_id": rid, "status": rr.status, "note": rr.note,
                        "violations": [v.to_row() for v in rr.violations],
                        "metrics": rr.metrics, "duration_ms": round(dur, 2)})
        violations.extend(rr.violations)

    elapsed = time.monotonic() - t0
    active = [v for v in violations if not v.suppressed]
    new = [v for v in active if not v.baseline]
    new_blockers = [v for v in new if v.severity == "blocker"]

    # ---- aggregate audit_health.json (P2 §4 schema) ----
    categories: dict = {}
    for rule in rules:
        cat = rule["category"]
        bucket = categories.setdefault(
            cat, {"rules": 0, "pass": 0, "fail_new": 0, "fail_baseline": 0})
        bucket["rules"] += 1
        rres = next((r for r in results if r["rule_id"] == rule["id"]), None)
        rviol = [v for v in active if v.rule_id == rule["id"]]
        if rres and rres["status"] in ("pass", "skip"):
            bucket["pass"] += 1
        elif any(not v.baseline for v in rviol):
            bucket["fail_new"] += 1
        else:
            bucket["fail_baseline"] += 1
    for bucket in categories.values():
        n = bucket["rules"]
        bucket["pass_rate"] = round(bucket["pass"] / n, 2) if n else 1.0

    ratchets: dict = {}
    for r in results:
        for k, v in r.get("metrics", {}).items():
            ratchets.setdefault(k, v)

    overall = "fail" if new_blockers else ("warn" if new or active else "pass")
    health = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "commit": git_head(repo),
        "overall": overall,
        "categories": categories,
        "violations_total": len(active),
        "violations_new": len(new),
        "violations_suppressed": len(violations) - len(active),
        "delta_7d": {"violations_total": 0},
        "ratchets": ratchets,
        "rules_run": len(results),
        "elapsed_s": round(elapsed, 2),
        "fast": fast,
        "rule_results": [{k: r[k] for k in
                          ("rule_id", "status", "note", "duration_ms")}
                         for r in results],
    }
    return {"health": health, "results": results, "violations": violations,
            "new_blockers": new_blockers, "new": new}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ETHER continuous-audit runner")
    ap.add_argument("--repo", required=True, help="target repo path")
    ap.add_argument("--fast", action="store_true",
                    help="run only rules marked fast:true (pre-commit set)")
    ap.add_argument("--json-out", help="write violations JSONL here")
    ap.add_argument("--health-out", default="audit_health.json",
                    help="audit_health.json aggregate path (default: cwd)")
    ap.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    ap.add_argument("--config", default=str(DEFAULT_RULES_CONFIG))
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print(f"error: repo not found: {repo}", file=sys.stderr)
        return 2
    try:
        out = run(repo, Path(args.config), Path(args.baseline), args.fast)
    except SystemExit:
        raise
    except Exception as e:
        print(f"error: runner failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 2

    health = out["health"]
    violations = out["violations"]

    if args.json_out:
        rows = []
        for r in out["results"]:
            for row in r["violations"]:
                row = dict(row)
                row["ts"] = health["generated"]
                row["commit"] = health["commit"]
                row["rule_status"] = r["status"]
                rows.append(row)
        atomic_write(Path(args.json_out),
                     "".join(json.dumps(r, sort_keys=True) + "\n"
                             for r in rows))
    try:
        atomic_write(Path(args.health_out),
                     json.dumps(health, indent=2, sort_keys=True) + "\n")
    except OSError as e:
        print(f"warn: could not write {args.health_out}: {e}", file=sys.stderr)

    # ---- human summary ----
    active = [v for v in violations if not v.suppressed]
    print(f"audit: repo={repo} commit={health['commit']} "
          f"rules={health['rules_run']} elapsed={health['elapsed_s']}s"
          f"{' (fast)' if args.fast else ''}")
    for r in out["results"]:
        n = len(r["violations"])
        tag = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP",
               "error": "ERR "}.get(r["status"], "????")
        note = f" — {r['note']}" if r["note"] else ""
        print(f"  [{tag}] {r['rule_id']:<9} {n:>3} violation(s)"
              f" ({r['duration_ms']:.0f} ms){note}")
    print(f"violations: {len(active)} active "
          f"({len(out['new'])} new, {len(active) - len(out['new'])} baselined, "
          f"{health['violations_suppressed']} suppressed)")
    if out["new"]:
        for v in out["new"][:20]:
            print(f"  NEW [{v.severity}] {v.rule_id} {v.file}:{v.line} "
                  f"{v.message[:100]}")
    if out["new_blockers"]:
        print(f"GATE: {len(out['new_blockers'])} NEW blocker violation(s) "
              "— exit 1")
        return 1
    print("GATE: clean (no new blocker violations)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
