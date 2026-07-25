#!/usr/bin/env python3
"""@ETHER agentic flywheel — synergistic with Pipeline + confidence gates.

Push only when:
  smoke + pytest pass
  sandbox exit == 0
  audit.approved
  confidence >= min threshold

Otherwise retry agentic pipeline until max retries, then block push.
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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORT_DIR = ROOT / "memory" / "flywheel"
REPORT_PATH = REPORT_DIR / "latest.json"
HISTORY_PATH = REPORT_DIR / "history.jsonl"
FLYWHEEL_MD = ROOT / "FLYWHEEL.md"

DEFAULT_OBJECTIVE = (
    "write a python function is_even(n) that returns True if n is even; "
    "print(is_even(4)); print(is_even(5))"
)


def _env() -> Dict[str, str]:
    env = os.environ.copy()
    # ensure editable package + repo imports resolve in child processes
    pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + pp if pp else "")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def run(cmd: List[str], timeout: int = 600) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        p = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_env(),
        )
        return {
            "cmd": cmd,
            "returncode": p.returncode,
            "stdout": (p.stdout or "")[-8000:],
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


def git(*args: str) -> Dict[str, Any]:
    return run(["git", *args], timeout=120)


def print_step(name: str, data: Dict[str, Any]) -> None:
    flag = "OK" if data.get("ok") else "FAIL"
    print(f"  [{flag}] {name} ({data.get('duration_s', 0)}s)")
    if not data.get("ok"):
        err = (data.get("stderr") or data.get("stdout") or "").strip()
        if err:
            print("    ---")
            for line in err.splitlines()[-20:]:
                print(f"    {line}")
            print("    ---")


def run_pipeline_once(objective: str) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
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


def agentic_verify(objective: str, min_confidence: float, max_retries: int) -> Dict[str, Any]:
    attempts: List[Dict[str, Any]] = []
    best: Optional[Dict[str, Any]] = None

    for i in range(1, max_retries + 1):
        print(f"  [agentic] attempt {i}/{max_retries} ...")
        r = run_pipeline_once(objective)
        r["attempt"] = i
        gate = (
            r.get("status") == "complete"
            and r.get("sandbox_exit") == 0
            and r.get("audit_approved") is True
            and float(r.get("confidence") or 0.0) >= min_confidence
        )
        r["gate_pass"] = gate
        attempts.append(r)
        if best is None or r["confidence"] > best["confidence"]:
            best = r
        print(
            f"  [agentic] conf={r['confidence']:.3f} audit={r['audit_approved']} "
            f"sandbox={r['sandbox_exit']} gate={'PASS' if gate else 'FAIL'}"
        )
        if gate:
            return {"ok": True, "attempts": attempts, "final": r, "best": best, "reason": "gates_passed"}

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

    steps["pull"] = git("pull", "--ff-only", "origin", "main")
    print_step("pull", steps["pull"])

    py = sys.executable
    steps["smoke"] = run([py, "scripts/smoke_test.py"], timeout=120)
    print_step("smoke", steps["smoke"])

    steps["pytest"] = run([py, "-m", "pytest", "-q", "--tb=line"], timeout=300)
    print_step("pytest", steps["pytest"])

    if run_doctor:
        steps["doctor"] = run([py, "-c", "from cli.main import app; app(['doctor'])"], timeout=60)
        print_step("doctor", steps["doctor"])

    static_ok = steps["smoke"]["ok"] and steps["pytest"]["ok"]

    if not static_ok:
        agentic = {
            "ok": False,
            "reason": "static_gates_failed",
            "attempts": [],
            "final": None,
            "best": None,
        }
        print("  [agentic] skipped — fix smoke/pytest first")
    else:
        agentic = agentic_verify(objective, min_confidence=min_confidence, max_retries=max_retries)

    gates_pass = static_ok and agentic["ok"]
    conf = float((agentic.get("final") or {}).get("confidence") or 0.0)
    audit = bool((agentic.get("final") or {}).get("audit_approved"))

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
                "stderr_tail": (data.get("stderr") or "")[-500:],
                "stdout_tail": (data.get("stdout") or "")[-500:],
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

    lines = [
        "# @ETHER Flywheel (agentic)",
        "",
        f"> Last cycle: **{ts}**  ",
        f"> Result: **{'PASS — push allowed' if gates_pass else 'FAIL — push blocked'}**  ",
        f"> Confidence: **{conf:.3f}** (min {min_confidence}) · Audit: **{audit}**",
        "",
        "| Step | OK | Duration |",
        "|------|----|----------|",
    ]
    for name, data in report["steps"].items():
        lines.append(f"| {name} | {'yes' if data['ok'] else 'NO'} | {data['duration_s']}s |")
    lines.append("")
    FLYWHEEL_MD.write_text("\n".join(lines), encoding="utf-8")

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
                    print(f"  [push] {'OK' if push['ok'] else 'FAILED'}")
                else:
                    report["pushed"] = False
                    print(f"  [push] commit failed: {(commit.get('stderr') or '')[-200:]}")
            else:
                report["pushed"] = True
                print("  [push] nothing to commit")
        REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="@ETHER agentic flywheel")
    parser.add_argument("--push", action="store_true")
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=float(os.getenv("ETHER_FLYWHEEL_MIN_CONFIDENCE", "0.7")),
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=int(os.getenv("ETHER_FLYWHEEL_MAX_RETRIES", "3")),
    )
    parser.add_argument(
        "--objective",
        type=str,
        default=os.getenv("ETHER_FLYWHEEL_OBJECTIVE", DEFAULT_OBJECTIVE),
    )
    parser.add_argument("--no-doctor", action="store_true")
    parser.add_argument("--loop", type=int, default=0)
    args = parser.parse_args(argv)

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

    print(f"Outer loop every {args.loop}s (push still gated). Ctrl+C to stop.")
    while True:
        code = once()
        print(f"--- sleep {args.loop}s (last exit={code}) ---")
        time.sleep(args.loop)


if __name__ == "__main__":
    raise SystemExit(main())
