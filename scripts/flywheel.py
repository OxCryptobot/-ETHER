#!/usr/bin/env python3
"""@ETHER autonomous agentic flywheel.

Fully hands-off mode:
  python scripts/flywheel.py --autonomous
  ether flywheel --autonomous

Loads .env automatically. Never pushes unless confidence+audit gates pass.
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

from core.dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

REPORT_DIR = ROOT / "memory" / "flywheel"
REPORT_PATH = REPORT_DIR / "latest.json"
HISTORY_PATH = REPORT_DIR / "history.jsonl"
FLYWHEEL_MD = ROOT / "FLYWHEEL.md"
HEARTBEAT_PATH = REPORT_DIR / "heartbeat.txt"

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
    env.setdefault("ETHER_SANDBOX_RETRY", "1")
    return env


def run(cmd: List[str], timeout: int = 600) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        p = subprocess.run(
            cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout, env=_env()
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
    print(f"  [{flag}] {name} ({data.get('duration_s', 0)}s)", flush=True)
    if not data.get("ok"):
        err = (data.get("stderr") or data.get("stdout") or "").strip()
        for line in err.splitlines()[-12:]:
            print(f"    {line}", flush=True)


def run_pipeline_once(objective: str) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        from core.pipeline import Pipeline

        result = Pipeline().run(objective, critique=False)
        audit_ok = bool(result.audit and result.audit.approved)
        confidence = float(result.confidence or 0.0)
        sandbox_ok = bool(result.sandbox and result.sandbox.exit_code == 0)
        stderr = (result.sandbox.stderr or "")[-800:] if result.sandbox else ""
        stdout = (result.sandbox.stdout or "")[-400:] if result.sandbox else ""
        return {
            "ok": result.status == "complete" and sandbox_ok and audit_ok,
            "status": result.status,
            "confidence": confidence,
            "audit_approved": audit_ok,
            "sandbox_exit": result.sandbox.exit_code if result.sandbox else None,
            "sandbox_stderr": stderr,
            "sandbox_stdout": stdout,
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
            "retries_inside_pipeline": 0,
            "error": str(e),
            "duration_s": round(time.perf_counter() - started, 3),
            "task_id": None,
        }


def agentic_verify(objective: str, min_confidence: float, max_retries: int) -> Dict[str, Any]:
    attempts: List[Dict[str, Any]] = []
    best: Optional[Dict[str, Any]] = None
    for i in range(1, max_retries + 1):
        print(f"  [agentic] attempt {i}/{max_retries} ...", flush=True)
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
            f"sandbox={r['sandbox_exit']} gate={'PASS' if gate else 'FAIL'}",
            flush=True,
        )
        if not gate and r.get("sandbox_stderr"):
            print(f"    stderr: {r['sandbox_stderr'][:240].replace(chr(10), ' ')}", flush=True)
        if gate:
            if r.get("sandbox_stdout"):
                print(f"    stdout: {r['sandbox_stdout'][:200].replace(chr(10), ' | ')}", flush=True)
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
        "# @ETHER Flywheel (autonomous)",
        "",
        f"> Last cycle: **{report['timestamp']}**  ",
        f"> Result: **{'PASS' if report['ok'] else 'FAIL'}**  ",
        f"> Confidence: **{g['confidence']:.3f}** (min {g['min_confidence']}) · Audit: **{g['audit_approved']}**  ",
        f"> Pushed: **{report.get('pushed')}** · Model: `{report.get('model', '')}`",
        "",
        "Hands-off launcher: `scripts/autonomy.ps1` or `ether flywheel --autonomous`",
        "",
    ]
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
    HEARTBEAT_PATH.write_text(ts, encoding="utf-8")
    steps: Dict[str, Any] = {}

    steps["pull"] = git("pull", "--ff-only", "origin", "main")
    print_step("pull", steps["pull"])

    # reload .env after pull (remote may update defaults)
    load_dotenv(ROOT / ".env", override=False)

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
        agentic = {"ok": False, "reason": "static_gates_failed", "attempts": [], "final": None, "best": None}
        print("  [agentic] skipped — static gates failed", flush=True)
    else:
        agentic = agentic_verify(objective, min_confidence=min_confidence, max_retries=max_retries)

    gates_pass = static_ok and agentic["ok"]
    final = agentic.get("final") or {}
    conf = float(final.get("confidence") or 0.0)
    audit = bool(final.get("audit_approved"))

    # push intent: explicit flag OR env autonomy setting
    want_push = do_push or os.getenv("ETHER_FLYWHEEL_PUSH", "0") == "1"

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
            n: {"ok": d["ok"], "returncode": d["returncode"], "duration_s": d["duration_s"]}
            for n, d in steps.items()
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

    if want_push:
        if not gates_pass:
            print(
                f"  [push] BLOCKED — conf={conf:.3f} audit={audit} static={static_ok}",
                flush=True,
            )
        else:
            git("add", "FLYWHEEL.md", "memory/flywheel/latest.json", "memory/flywheel/history.jsonl")
            status = git("status", "--porcelain")
            if status.get("stdout", "").strip():
                msg = f"flywheel PASS conf={conf:.3f} audit=ok @ {ts}"
                commit = git("commit", "-m", msg)
                if commit["ok"] or commit["returncode"] == 0:
                    push = git("push", "origin", "HEAD")
                    report["pushed"] = push["ok"]
                    print(f"  [push] {'OK' if push['ok'] else 'FAILED'}", flush=True)
                else:
                    print("  [push] commit failed", flush=True)
            else:
                report["pushed"] = True
                print("  [push] nothing to commit", flush=True)
        REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report


def show_status() -> int:
    if not REPORT_PATH.exists():
        print("No flywheel report yet.")
        return 1
    data = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "timestamp": data.get("timestamp"),
                "ok": data.get("ok"),
                "push_allowed": data.get("push_allowed"),
                "pushed": data.get("pushed"),
                "confidence": data.get("gates", {}).get("confidence"),
                "audit_approved": data.get("gates", {}).get("audit_approved"),
                "model": data.get("model"),
                "agentic_reason": data.get("gates", {}).get("agentic_reason"),
                "heartbeat": HEARTBEAT_PATH.read_text(encoding="utf-8").strip()
                if HEARTBEAT_PATH.exists()
                else None,
            },
            indent=2,
        )
    )
    return 0 if data.get("ok") else 1


def main(argv: Optional[List[str]] = None) -> int:
    load_dotenv(ROOT / ".env")

    parser = argparse.ArgumentParser(description="@ETHER autonomous flywheel")
    parser.add_argument("--push", action="store_true", help="push if gates pass")
    parser.add_argument("--status", action="store_true", help="show last report")
    parser.add_argument(
        "--autonomous",
        action="store_true",
        help="hands-off loop forever using .env (push gated)",
    )
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
        "--interval",
        type=int,
        default=int(os.getenv("ETHER_FLYWHEEL_INTERVAL", "900")),
        help="seconds between autonomous cycles",
    )
    parser.add_argument(
        "--objective",
        type=str,
        default=os.getenv("ETHER_FLYWHEEL_OBJECTIVE", DEFAULT_OBJECTIVE),
    )
    parser.add_argument("--no-doctor", action="store_true")
    parser.add_argument("--loop", type=int, default=0, help="alias for interval outer loop")
    args = parser.parse_args(argv)

    if args.status:
        return show_status()

    # autonomous => continuous + push intent from env/flag
    continuous = args.autonomous or args.loop > 0
    interval = args.interval if args.autonomous else (args.loop or args.interval)
    do_push = args.push or args.autonomous or os.getenv("ETHER_FLYWHEEL_PUSH", "0") == "1"

    def once() -> int:
        report = cycle(
            do_push=do_push,
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
            ),
            flush=True,
        )
        return 0 if report["ok"] else 1

    if not continuous:
        return once()

    print(
        f"@ETHER AUTONOMOUS on — interval={interval}s push_gated=True "
        f"model={os.getenv('ETHER_PRIMARY_MODEL', '')}",
        flush=True,
    )
    while True:
        try:
            code = once()
            print(f"--- cycle done exit={code}; sleep {interval}s ---", flush=True)
        except KeyboardInterrupt:
            print("Autonomous loop stopped.", flush=True)
            return 0
        except Exception as e:
            print(f"--- cycle error: {e}; sleep {interval}s ---", flush=True)
        time.sleep(max(30, interval))


if __name__ == "__main__":
    raise SystemExit(main())
