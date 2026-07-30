#!/usr/bin/env python3
"""P3 ingest adapter: validate + normalize incoming violations JSONL.

This is the single seam between P2 (emitter) and P3 (classifier): if the
emitter's schema ever changes, only this file changes (P3 §0).

Usage:
    python tools/audit/ingest.py violations.jsonl [--out clean.jsonl]
        [--scan-fp /path/to/repo]

Also scans a repo for `# audit-fp: RULE-ID <reason>` markers (P3 §8) and
reports them for fp_feedback to record.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REQUIRED = {
    "rule_id": str,
    "category": str,
    "severity": str,
    "file": str,
    "line": int,
    "message": str,
    "fingerprint": str,
    "finding_ids": list,
}
OPTIONAL_DEFAULTS = {
    "pattern_hash": "",
    "context": "",
    "module": "",
    "baseline": False,
    "suppressed": False,
    "ts": "",
    "commit": "",
}
SEVERITIES = {"blocker", "high", "med", "low", "warn"}
FP_MARKER = re.compile(r"#\s*audit-fp:\s*([A-Z]+-\d+)\s*(.*)")


def validate_row(row: dict, lineno: int) -> tuple:
    """(normalized_row, errors). Never raises."""
    errors = []
    out = {}
    for key, typ in REQUIRED.items():
        if key not in row:
            errors.append(f"row {lineno}: missing required key '{key}'")
            continue
        val = row[key]
        if not isinstance(val, typ):
            errors.append(
                f"row {lineno}: '{key}' has type {type(val).__name__}, "
                f"expected {typ.__name__}")
            continue
        out[key] = val
    for key, default in OPTIONAL_DEFAULTS.items():
        out[key] = row.get(key, default)
    sev = out.get("severity")
    if sev and sev not in SEVERITIES:
        errors.append(f"row {lineno}: unknown severity '{sev}'")
    if out.get("rule_id") and not re.match(r"^[A-Z]+-\d+$", out["rule_id"]):
        errors.append(f"row {lineno}: malformed rule_id '{out['rule_id']}'")
    return out, errors


def ingest(path: Path) -> tuple:
    """(rows, errors, dropped)."""
    rows, errors, dropped = [], [], 0
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as e:
            errors.append(f"row {i}: invalid JSON: {e}")
            dropped += 1
            continue
        row, errs = validate_row(raw, i)
        if errs:
            errors.extend(errs)
            dropped += 1
            continue
        rows.append(row)
    return rows, errors, dropped


def scan_fp_markers(repo: Path) -> list:
    """Find `# audit-fp:` markers in the repo (P3 §8 path 2)."""
    found = []
    for p in sorted(repo.rglob("*.py")):
        if any(part in {".git", ".venv", "__pycache__"} for part in p.parts):
            continue
        try:
            for i, line in enumerate(
                    p.read_text(encoding="utf-8", errors="replace")
                    .splitlines(), 1):
                m = FP_MARKER.search(line)
                if m:
                    found.append({
                        "file": p.relative_to(repo).as_posix(),
                        "line": i,
                        "rule_id": m.group(1),
                        "reason": m.group(2).strip(),
                    })
        except OSError:
            continue
    return found


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="P2 JSONL ingest adapter")
    ap.add_argument("jsonl", help="violations JSONL to validate")
    ap.add_argument("--out", help="write normalized rows here")
    ap.add_argument("--scan-fp", help="repo path to scan for # audit-fp markers")
    args = ap.parse_args(argv)

    rows, errors, dropped = ingest(Path(args.jsonl))
    print(f"ingest: {len(rows)} valid rows, {dropped} dropped, "
          f"{len(errors)} error(s)")
    for e in errors[:20]:
        print(f"  {e}")
    if args.out:
        Path(args.out).write_text(
            "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows),
            encoding="utf-8")
        print(f"wrote {len(rows)} rows -> {args.out}")
    if args.scan_fp:
        markers = scan_fp_markers(Path(args.scan_fp))
        print(f"# audit-fp markers: {len(markers)}")
        for m in markers:
            print(f"  {m['file']}:{m['line']} {m['rule_id']} {m['reason']}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
