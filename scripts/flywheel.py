#!/usr/bin/env python3
"""@ETHER agentic flywheel

Gates:
  - smoke + pytest must pass
  - ether pipeline must produce audit.approved == True
  - confidence >= ETHER_FLYWHEEL_MIN_CONFIDENCE (default 0.7)

If confidence/audit fail → retry pipeline (self-heal) up to N times.
Push is allowed ONLY when all gates pass.

Usage:
  python scripts/flywheel.py
  python scripts/flywheel.py --push
  python scripts/flywheel.py --push --min-confidence 0.8 --max-retries 3
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

DEFAULT_OBJECTIVE = (
    "write a python function is_even(n) that returns True if n is even; "
    "print(is_even(4)); print(is_even(5))"
)


def run(cmd: List[str], timeout: int = 600, env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    started = time.perf_counter()
    merged = os.environ.copy()
    if env:
        merged.update(env)
    try:
        p = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=merged,
        )
        return {
            "cmd": cmd,
            "returncode": p.returncode,
            "stdout": (p.stdout or "")[-6000:],
            "stderr": (p.stderr or "")[-4000:],
            "duration_s": round(time.perf_counter() - started, 3),
            "ok": p.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {
            "cmd": cmd,
            "returncode": -1,
            "stdout": "",
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


def run_pipeline_once(objective: str) -> Dict[str, Any]:
    """Run in-process pipeline for confidence/audit gates."""
    started = time.perf_counter()
    try:
        sys.path.insert(0, str(ROOT))
        from core.pipeline import Pipeline

        result = Pipeline().run(objective, critique=False)
        audit_ok = bool(result.audit and result.audit.approved)
        confidence = float(result.confidence or 0.0)
        sandbox_ok = bool(result.sandbox and result.sandbox.exit_code == 0)
        return {
            "ok": result.status == "complete" and sandbox_ok and audit_ok,
            "status": result.status,
            "confidence": confidence,
            "audit_approved": audit_ok,
            "sandbox_exit": result.sandbox.exit_code if result.sandbox else None,
            "retries_inside_pipeline": result.retries,
            "error": result.error,
            "duration_s": round(time.perf_counter() - started, 3),
            "task_id": str(result.task_id),
        }
    except Exception as e:
        return {
            "ok": False,
            "status": "exception",
            "confidence": 0.0,
            "audit_approved": False,
            "sandbox_exit": None,
            "retries_inside_pipeline": 0,
            "error": str(e),
            "duration_s": round(time.perf_counter() - started, 3),
            "task_id": None,
        }


def agentic_verify(
    objective: str,
    min_confidence: float,
    max_retries: int,
) -> Dict[str, Any]:
    """Retry pipeline until confidence + audit gates pass or attempts exhausted."""
    attempts: List[Dict[str, Any]] = []
    best: Optional[Dict[str, Any]] = None

    for i in range(1, max_retries + 1):
        print(f"  [agentic] attempt {i}/{max_retries} ...")
        r = run_pipeline_once(objective)
        r["attempt"] = i
        attempts.append(r)

        if best is None or r["confidence"] > best["confidence"]:
            best = r

        gate = (
            r.get("status") == "complete"
            and r.get("sandbox_exit") == 0
            and r.get("audit_approved") is True
            and float(r.get("confidence") or 0.0) >= min_confidence
        )
        r["gate_pass"] = gate
        print(
            f"  [agentic] conf={r['confidence']:.3f} audit={r['audit_approved']} "
            f"sandbox={r['sandbox_exit']} gate={'PASS' if gate else 'FAIL'}"
        )
        if gate:
            return {
                "ok": True,
                "attempts": attempts,
                "final": r,
                "best": best,
                "reason": "gates_passed",
            }

    return {
        "ok": False,
        "attempts": attempts,
        "final": attempts[-1] if attempts else None,
        "best": best,
        "reason": "max_retries_exhausted",
    }


def cycle(
    do_push: bool,
    min_confidence: float,
    max_retries: int,
    objective: str,
    run_doctor: bool,
) -> Dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    steps: Dict[str, Any] = {}

    # 1) pull latest code
    steps["pull"] = git("pull", "--ff-only", "origin", "main")

    # 2) static quality gates
    py = sys.executable
    steps["smoke"] = run([py, "scripts/smoke_test.py"], timeout=120)
    steps["pytest"] = run([py, "-m", "pytest", "-q", "--tb=line"], timeout=300)
    if run_doctor:
        steps["doctor"] = run([py, "-c", "from cli.main import app; app(['doctor'])"], timeout=60)

    static_ok = steps["smoke"]["ok"] and steps["pytest"]["ok"]

    # 3) agentic confidence gate (only if static ok)
    agentic: Dict[str, Any]
    if not static_ok:
        agentic = {
            "ok": False,
            "reason": "static_gates_failed",
            "attempts": [],
            "final": None,
            "best": None,
        }
        print("  [agentic] skipped — smoke/pytest failed")
    else:
        agentic = agentic_verify(objective, min_confidence=min_confidence, max_retries=max_retries)

    gates_pass = static_ok and agentic["ok"]
    conf = 0.0
    audit = False
    if agentic.get("final"):
        conf = float(agentic["final"].get("confidence") or 0.0)
        audit = bool(agentic["final"].get("audit_approved"))

    report: Dict[str, Any] = {
        "timestamp": ts,
        "host": os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "unknown",
        "python": sys.version.split()[0],
        "ok": gates_pass,
        "gates": {
            "static_ok": static_ok,
            "agentic_ok": agentic["ok"],
            "min_confidence": min_confidence,
            "confidence": conf,
            "audit_approved": audit,
            "max_retries": max_retries,
            "agentic_reason": agentic.get("reason"),
        },
        "objective": objective,
        "steps": {
            name: {
                "ok": data["ok"],
                "returncode": data["returncode"],
                "duration_s": data["duration_s"],
                "stderr_tail": (data.get("stderr") or "")[-400:],
            }
            for name, data in steps.items()
        },
        "agentic": {
            "ok": agentic["ok"],
            "reason": agentic.get("reason"),
            "attempts": [
                {
                    "attempt": a.get("attempt"),
                    "confidence": a.get("confidence"),
                    "audit_approved": a.get("audit_approved"),
                    "sandbox_exit": a.get("sandbox_exit"),
                    "gate_pass": a.get("gate_pass"),
                    "error": a.get("error"),
                }
                for a in agentic.get("attempts", [])
            ],
        },
        "push_allowed": gates_pass,
        "pushed": False,
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    with HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(report) + "\n")

    # markdown dashboard
    lines = [
        "# @ETHER Flywheel (agentic)",
        "",
        f"> Last cycle: **{ts}**  ",
        f"> Host: `{report['host']}`  ",
        f"> Result: **{'PASS — push allowed' if gates_pass else 'FAIL — push blocked'}**  ",
        f"> Confidence: **{conf:.3f}** (min {min_confidence})  ",
        f"> Audit approved: **{audit}**",
        "",
        "## Gates",
        f"- static (smoke+pytest): {'PASS' if static_ok else 'FAIL'}",
        f"- agentic (sandbox+audit+confidence): {'PASS' if agentic['ok'] else 'FAIL'} ({agentic.get('reason')})",
        "",
        "| Step | OK | Duration | Code |",
        "|------|----|----------|------|",
    ]
    for name, data in report["steps"].items():
        lines.append(
            f"| {name} | {'yes' if data['ok'] else 'NO'} | {data['duration_s']}s | {data['returncode']} |"
        )
    lines.append("")
    lines.append("## Agentic attempts")
    if report["agentic"]["attempts"]:
        lines.append("| Attempt | Confidence | Audit | Sandbox | Gate |")
        lines.append("|---------|------------|-------|---------|------|")
        for a in report["agentic"]["attempts"]:
            lines.append(
                f"| {a['attempt']} | {a['confidence']:.3f} | {a['audit_approved']} | "
                f"{a['sandbox_exit']} | {'PASS' if a.get('gate_pass') else 'FAIL'} |"
            )
    else:
        lines.append("_No agentic attempts (static failed or skipped)._")
    lines.extend(
        [
            "",
            "## Policy",
            "- **No push** unless static + agentic gates pass",
            "- Agentic retries until confidence/audit met or max retries",
            "- Only `FLYWHEEL.md` and `memory/flywheel/*` are committed",
            "",
        ]
    )
    FLYWHEEL_MD.write_text("\n".join(lines), encoding="utf-8")

    # 4) push ONLY if gates pass
    if do_push or os.getenv("ETHER_FLYWHEEL_PUSH", "0") == "1":
        if not gates_pass:
            report["pushed"] = False
            report["push_blocked_reason"] = (
                f"gates failed (confidence={conf:.3f}, audit={audit}, static={static_ok})"
            )
            print(f"  [push] BLOCKED — {report['push_blocked_reason']}")
        else:
            git("add", "FLYWHEEL.md", "memory/flywheel/latest.json", "memory/flywheel/history.jsonl")
            status = git("status", "--porcelain")
            if status.get("stdout", "").strip():
                msg = f"flywheel PASS conf={conf:.3f} audit=ok @ {ts}"
                commit = git("commit", "-m", msg)
                if commit["ok"] or commit["returncode"] == 0:
                    push = git("push", "origin", "HEAD")
                    report["pushed"] = push["ok"]
                    report["push_stderr"] = (push.get("stderr") or "")[-300:]
                    print(f"  [push] {'OK' if push['ok'] else 'FAILED'}")
                else:
                    report["pushed"] = False
                    report["push_stderr"] = (commit.get("stderr") or "")[-300:]
            else:
                report["pushed"] = True
                report["push_stderr"] = "nothing to commit"
                print("  [push] nothing to commit")
        REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="@ETHER agentic flywheel")
    parser.add_argument("--push", action="store_true", help="push ONLY if gates pass")
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=float(os.getenv("ETHER_FLYWHEEL_MIN_CONFIDENCE", "0.7")),
        help="minimum confidence to allow push (default 0.7)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=int(os.getenv("ETHER_FLYWHEEL_MAX_RETRIES", "3")),
        help="agentic pipeline retries until gates pass",
    )
    parser.add_argument(
        "--objective",
        type=str,
        default=os.getenv("ETHER_FLYWHEEL_OBJECTIVE", DEFAULT_OBJECTIVE),
        help="coding objective used for confidence gate",
    )
    parser.add_argument("--no-doctor", action="store_true")
    parser.add_argument(
        "--loop",
        type=int,
        default=0,
        help="optional outer loop seconds (0=once). Still never pushes unless gates pass.",
    )
    args = parser.parse_args()

    def once() -> int:
        report = cycle(
            do_push=args.push,
            min_confidence=args.min_confidence,
            max_retries=max(1, args.max_retries),
            objective=args.objective,
            run_doctor=not args.no_doctor,
        )
        print(
            json.dumps(
                {
                    "ok": report["ok"],
                    "push_allowed": report["push_allowed"],
                    "pushed": report.get("pushed", False),
                    "confidence": report["gates"]["confidence"],
                    "audit_approved": report["gates"]["audit_approved"],
                    "timestamp": report["timestamp"],
                },
                indent=2,
            )
        )
        return 0 if report["ok"] else 1

    if args.loop <= 0:
        return once()

    print(f"Flywheel outer loop every {args.loop}s (push still gated). Ctrl+C to stop.")
    while True:
        code = once()
        print(f"--- sleep {args.loop}s (last exit={code}) ---")
        time.sleep(args.loop)


if __name__ == "__main__":
    raise SystemExit(main())
