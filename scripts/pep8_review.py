"""CLI for ETHER embedded PEP8 reviewer.

  python -m scripts.pep8_review core/ scripts/
  python -m scripts.pep8_review --json artifacts/pep8_report.json core/
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ETHER PEP8 / ruff reviewer")
    ap.add_argument("paths", nargs="*", default=["core", "scripts"])
    ap.add_argument("--json", dest="json_out", default="")
    ap.add_argument("--md", dest="md_out", default="")
    args = ap.parse_args(argv)

    from core.pep8_reviewer import format_report_md, review_paths

    report = review_paths(args.paths)
    md = format_report_md(report)
    print(md, flush=True)

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
        print(f"json: {out}", flush=True)
    if args.md_out:
        out = Path(args.md_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        print(f"md: {out}", flush=True)

    # ok means no critical; warnings still exit 0 so host continue_on_fail can use it
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
