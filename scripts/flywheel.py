#!/usr/bin/env python3
"""@ETHER agentic flywheel — Pipeline + confidence/audit gated push.

Push only when smoke+pytest pass AND sandbox exit 0 AND audit approved
AND confidence >= threshold. Retries agentic pipeline until max retries.
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

# Deterministic, short objective — easier for 3B local coders to nail
DEFAULT_OBJECTIVE = (
    "Write only this Python code with no markdown:\n"
    "def is_even(n):\n"
    "    return n % 2 == 0\n"
    "print(is_even(4))\n"
    "print(is_even(5))\n"
)


def _env() -> Dict[str, str]:
    env = os.environ.copy()
    pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + pp if pp else "")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    # ensure sandbox retry inside Pipeline is on during flywheel
    env.setdefault("ETHER_SANDBOX_RETRY", "1")
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
            for line in err.splitlines()[-15:]:
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
        stderr = ""
        stdout = ""
        if result.sandbox:
            stderr = (result.sandbox.stderr or "")[-800:]
            stdout = (result.sandbox.stdout or "")[-400:]
        code_preview = (result.generated_code or "")[:300]
        return {
            "ok": result.status == "complete" and sandbox_ok and audit_ok,
            "status": result.status,
            "confidence": confidence,
            "audit_approved": audit_ok,
            "sandbox_exit": result.sandbox.exit_code if result.sandbox else None,
            "sandbox_stderr": stderr,
            "sandbox_stdout": stdout,
            "code_preview": code_preview,
            "retries_inside_pipeline": getattr(result, "retries", 0),
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
            "sandbox_stderr": str(e),
            "sandbox_stdout": "",
            "code_preview": "",
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
        if not gate:
            if r.get("sandbox_stderr"):
                print(f"    stderr: {r['sandbox_stderr'][:300].replace(chr(10), ' ')}")
            if r.get("error"):
                print(f"    error: {r['error'][:200]}")
        if gate:
            if r.get("sandbox_stdout"):
                print(f"    stdout: {r['sandbox_stdout'][:200].replace(chr(10), ' | ')}")
            return {"ok": True, "attempts": attempts, "final": r, "best": best, "reason": "gates_passed"}

    return {
        "ok": False,
        "attempts": attempts,
        "final": attempts[-1] if attempts else None,
        "best": best,
        "reason": "max_retries_exhausted",
    }


def write_dashboard(report: Dict[str, Any]) -> None:
    g = report["gates"]
    lines = [
        "# @ETHER Flywheel (agentic)",
        "",
        f"> Last cycle: **{report['timestamp']}**  ",
        f"> Result: **{'PASS — push allowed' if report['ok'] else 'FAIL — push blocked'}**  ",
        f"> Confidence: **{g['confidence']:.3f}** (min {g['min_confidence']}) · Audit: **{g['audit_approved']}**  ",
        f"> Host: `{report.get('host', '?')}` · model hint: `{os.getenv('ETHER_PRIMARY_MODEL', '')}`",
        "",
        "| Step | OK | Duration |",
        "|------|----|----------|",
    ]
    for name, data in report["steps"].items():
        lines.append(f"| {name} | {'yes' if data['ok'] else 'NO'} | {data['duration_s']}s |")
    lines.append("")
    lines.append("## Agentic attempts")
    if report["agentic"]["attempts"]:
        lines.append("| # | Conf | Audit | Sandbox | Gate |")
        lines.append("|---|------|-------|---------|------|")
        for a in report["agentic"]["attempts"]:
            lines.append(
                f"| {a['attempt']} | {a['confidence']:.3f} | {a['audit_approved']} | "
                f"{a['sandbox_exit']} | {'PASS' if a.get('gate_pass') else 'FAIL'} |"
            )
    else:
        lines.append("_No agentic attempts._")
    lines.extend(
        [
            "",
            "## Policy",
            "- Push only if static + agentic gates pass",
            "- Agentic retries until confidence/audit met",
            "",
            "```powershell",
            "ether flywheel",
            "ether flywheel --push",
            "ether flywheel --status",
            "```",
            "",
        ]
    )
    FLYWHEEL_MD.write_text("\n".join(lines), encoding="utf-8")


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
    final = agentic.get("final") or {}
    conf = float(final.get("confidence") or 0.0)
    audit = bool(final.get("audit_approved"))

    report: Dict[str, Any] = {
        "timestamp": ts,
        "host": os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "unknown",
        "python": sys.version.split()[0],
        "model": os.getenv("ETHER_PRIMARY_MODEL", ""),
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
        "objective": objective[:200],
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
                    "stderr": (a.get("sandbox_stderr") or "")[:300],
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
    write_dashboard(report)

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
                    if not push["ok"]:
                        print(f"    {(push.get('stderr') or '')[-200:]}")
                else:
                    report["pushed"] = False
                    print(f"  [push] commit failed")
            else:
                report["pushed"] = True
                print("  [push] nothing to commit (already clean)")
        REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report


def show_status() -> int:
    if not REPORT_PATH.exists():
        print("No flywheel report yet. Run: ether flywheel")
        return 1
    data = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    print(json.dumps({
        "timestamp": data.get("timestamp"),
        "ok": data.get("ok"),
        "push_allowed": data.get("push_allowed"),
        "pushed": data.get("pushed"),
        "confidence": data.get("gates", {}).get("confidence"),
        "audit_approved": data.get("gates", {}).get("audit_approved"),
        "model": data.get("model"),
        "agentic_reason": data.get("gates", {}).get("agentic_reason"),
    }, indent=2))
    return 0 if data.get("ok") else 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="@ETHER agentic flywheel")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--status", action="store_true", help="show last report only")
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

    if args.status:
        return show_status()

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
