#!/usr/bin/env python3
"""@ETHER local flywheel

Cycle:
  1. git pull --ff-only
  2. run smoke + pytest
  3. write report under memory/flywheel/
  4. update FLYWHEEL.md
  5. optional commit + push (ETHER_FLYWHEEL_PUSH=1)

Usage:
  python scripts/flywheel.py
  python scripts/flywheel.py --push
  python scripts/flywheel.py --loop 300
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "memory" / "flywheel"
REPORT_PATH = REPORT_DIR / "latest.json"
HISTORY_PATH = REPORT_DIR / "history.jsonl"
FLYWHEEL_MD = ROOT / "FLYWHEEL.md"


def run(cmd: List[str], timeout: int = 600) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        p = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        return {
            "cmd": cmd,
            "returncode": p.returncode,
            "stdout": (p.stdout or "")[-4000:],
            "stderr": (p.stderr or "")[-4000:],
            "duration_s": round(time.perf_counter() - started, 3),
            "ok": p.returncode == 0,
        }
    except subprocess.TimeoutExpired as e:
        return {
            "cmd": cmd,
            "returncode": -1,
            "stdout": (e.stdout or "") if isinstance(e.stdout, str) else "",
            "stderr": f"TIMEOUT after {timeout}s",
            "duration_s": round(time.perf_counter() - started, 3),
            "ok": False,
        }
    except Exception as e:
        return {
            "cmd": cmd,
            "returncode": -1,
            "stdout": "",
            "stderr": str(e),
            "duration_s": round(time.perf_counter() - started, 3),
            "ok": False,
        }


def git(*args: str, timeout: int = 120) -> Dict[str, Any]:
    return run(["git", *args], timeout=timeout)


def cycle(do_push: bool = False, run_ether_doctor: bool = True) -> Dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    steps: Dict[str, Any] = {}

    # 1) pull
    steps["pull"] = git("pull", "--ff-only", "origin", "main")

    # 2) tests
    py = sys.executable
    steps["smoke"] = run([py, "scripts/smoke_test.py"], timeout=120)
    steps["pytest"] = run([py, "-m", "pytest", "-q", "--tb=no"], timeout=300)

    if run_ether_doctor:
        # prefer module invocation so PATH is not required
        steps["doctor"] = run([py, "-c", "from cli.main import app; app(['doctor'])"], timeout=60)

    # 3) summary
    ok = all(steps[k]["ok"] for k in ("smoke", "pytest") if k in steps)
    report = {
        "timestamp": ts,
        "host": os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "unknown",
        "python": sys.version.split()[0],
        "ok": ok,
        "steps": {
            name: {
                "ok": data["ok"],
                "returncode": data["returncode"],
                "duration_s": data["duration_s"],
                "stderr_tail": (data.get("stderr") or "")[-500:],
            }
            for name, data in steps.items()
        },
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    with HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(report) + "\n")

    # 4) markdown dashboard
    lines = [
        "# @ETHER Flywheel",
        "",
        f"> Last cycle: **{ts}**  ",
        f"> Host: `{report['host']}`  ",
        f"> Result: {'PASS' if ok else 'FAIL'}",
        "",
        "| Step | OK | Duration | Code |",
        "|------|----|----------|------|",
    ]
    for name, data in report["steps"].items():
        lines.append(
            f"| {name} | {'yes' if data['ok'] else 'NO'} | {data['duration_s']}s | {data['returncode']} |"
        )
    lines.extend(
        [
            "",
            "## How to run",
            "```powershell",
            "python scripts/flywheel.py",",
            "python scripts/flywheel.py --push",",
            "python scripts/flywheel.py --loop 300",",
            "```",
            "",
            "Set `ETHER_FLYWHEEL_PUSH=1` or pass `--push` to commit + push reports.",
            "",
        ]
    )
    FLYWHEEL_MD.write_text("\n".join(lines), encoding="utf-8")

    # 5) optional push (only flywheel artifacts)
    pushed = False
    if do_push or os.getenv("ETHER_FLYWHEEL_PUSH", "0") == "1":
        git("add", "FLYWHEEL.md", "memory/flywheel/latest.json")
        # history can grow; still useful
        git("add", "memory/flywheel/history.jsonl")
        status = git("status", "--porcelain")
        if status.get("stdout", "").strip():
            msg = f"flywheel: {'PASS' if ok else 'FAIL'} @ {ts}"
            commit = git("commit", "-m", msg)
            if commit["ok"] or commit["returncode"] == 0:
                push = git("push", "origin", "HEAD")
                pushed = push["ok"]
                report["push"] = {"ok": pushed, "stderr": push.get("stderr", "")[-300:]}
            else:
                report["push"] = {"ok": False, "stderr": commit.get("stderr", "")[-300:]}
        else:
            report["push"] = {"ok": True, "stderr": "nothing to commit"}
        REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    report["pushed"] = pushed
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="@ETHER local flywheel")
    parser.add_argument("--push", action="store_true", help="commit + push flywheel reports")
    parser.add_argument("--loop", type=int, default=0, help="repeat every N seconds (0 = once)")
    parser.add_argument("--no-doctor", action="store_true", help="skip ether doctor")
    args = parser.parse_args()

    def once() -> int:
        report = cycle(do_push=args.push, run_ether_doctor=not args.no_doctor)
        print(json.dumps({"ok": report["ok"], "timestamp": report["timestamp"], "pushed": report.get("pushed", False)}, indent=2))
        for name, step in report["steps"].items():
            flag = "OK" if step["ok"] else "FAIL"
            print(f"  [{flag}] {name} ({step['duration_s']}s)")
        return 0 if report["ok"] else 1

    if args.loop <= 0:
        return once()

    print(f"Flywheel loop every {args.loop}s. Ctrl+C to stop.")
    while True:
        code = once()
        print(f"--- sleep {args.loop}s (last exit={code}) ---")
        time.sleep(args.loop)


if __name__ == "__main__":
    raise SystemExit(main())
