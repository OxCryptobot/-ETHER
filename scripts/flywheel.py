#!/usr/bin/env python3
"""@ETHER autonomous agentic flywheel — git → local → sandbox → git (rinse, repeat)."""

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
from scripts.flywheel_git import safe_pull  # noqa: E402
from scripts.flywheel_metrics import pipeline_metrics  # noqa: E402

load_dotenv(ROOT / ".env")

REPORT_DIR = ROOT / "memory" / "flywheel"
REPORT_PATH = REPORT_DIR / "latest.json"
FAIL_PATH = REPORT_DIR / "last_fail.json"
HISTORY_PATH = REPORT_DIR / "history.jsonl"
FLYWHEEL_MD = ROOT / "FLYWHEEL.md"
HEARTBEAT_PATH = REPORT_DIR / "heartbeat.txt"

DEFAULT_OBJECTIVE = (
    "Write only Python with asserts:\n"
    "def is_even(n):\n"
    "    return n % 2 == 0\n"
    "assert is_even(4) is True\n"
    "assert is_even(5) is False\n"
    "print('ok')\n"
)

REPORT_PATHS = [
    "FLYWHEEL.md",
    "memory/flywheel/latest.json",
    "memory/flywheel/history.jsonl",
    "memory/flywheel/last_fail.json",
    "memory/flywheel/heartbeat.txt",
]


def _env() -> Dict[str, str]:
    env = os.environ.copy()
    pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + pp if pp else "")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("ETHER_SANDBOX_RETRY", "1")
    return env


def _compute_do_push(push_flag: bool) -> bool:
    """Report pushes are explicit opt-in only (MEAS-005).

    --autonomous previously implied push, flooding main with ~25 report
    commits/day. Autonomy ≠ consent to publish; only --push or
    ETHER_FLYWHEEL_PUSH=1 publishes.
    """
    return push_flag or os.getenv("ETHER_FLYWHEEL_PUSH", "0") == "1"


def run(cmd: List[str], timeout: int = 600) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        p = subprocess.run(
            cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout, env=_env()
        )
        out = {
            "cmd": cmd,
            "returncode": p.returncode,
            "stdout": (p.stdout or "")[-8000:],
            "stderr": (p.stderr or "")[-4000:],
            "duration_s": round(time.perf_counter() - started, 3),
            "ok": p.returncode == 0,
        }
        err = (out["stderr"] or out["stdout"] or "").strip()
        out["error_brief"] = err.splitlines()[-1][:180] if err and not out["ok"] else ""
        return out
    except subprocess.TimeoutExpired:
        return {
            "cmd": cmd,
            "returncode": -1,
            "stdout": "",
            "stderr": f"TIMEOUT after {timeout}s",
            "duration_s": round(time.perf_counter() - started, 3),
            "ok": False,
            "error_brief": f"TIMEOUT after {timeout}s",
        }
    except Exception as e:
        return {
            "cmd": cmd,
            "returncode": -1,
            "stdout": "",
            "stderr": str(e),
            "duration_s": round(time.perf_counter() - started, 3),
            "ok": False,
            "error_brief": str(e)[:180],
        }


def git(*args: str) -> Dict[str, Any]:
    return run(["git", *args], timeout=120)


def print_step(name: str, data: Dict[str, Any]) -> None:
    flag = "OK" if data.get("ok") else "FAIL"
    healed = data.get("healed")
    soft = data.get("soft")
    extra = ""
    if healed:
        extra += f" healed={healed}"
    if soft:
        extra += " soft"
    print(f"  [{flag}] {name} ({data.get('duration_s', 0)}s){extra}", flush=True)
    if not data.get("ok") or data.get("soft"):
        err = (data.get("stderr") or data.get("stdout") or data.get("error_brief") or "").strip()
        for line in err.splitlines()[-8:]:
            print(f"    {line}", flush=True)


def run_pipeline_once(objective: str, holdout_test: str = "") -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        from core.pipeline import Pipeline

        # Passed into the pipeline (not graded afterwards) so the holdout
        # verdict reaches compute_reward — otherwise the bandit trains purely
        # on assertions the model wrote about its own output.
        result = Pipeline().run(objective, critique=False, holdout_test=holdout_test)
        metrics = pipeline_metrics(result)
        metrics["duration_s"] = round(time.perf_counter() - started, 3)
        return metrics
    except Exception as e:
        return {
            "ok": False,
            "status": "exception",
            "confidence": 0.0,
            "verification_score": 0.0,
            "total_tests": 0,
            "audit_approved": False,
            "sandbox_exit": None,
            "sandbox_stderr": str(e),
            "sandbox_stdout": "",
            "retries_inside_pipeline": 0,
            "error": str(e),
            "duration_s": round(time.perf_counter() - started, 3),
            "task_id": None,
            "fail_kind": "exception",
        }


def agentic_verify(
    objective: str,
    min_confidence: float,
    max_retries: int,
    holdout_test: str = "",
) -> Dict[str, Any]:
    """Verify a generated artifact.

    When `holdout_test` is supplied, the artifact must additionally pass
    assertions the generator never saw. Self-authored assertions only show the
    code does what the model intended; a wrong implementation shipping its own
    passing asserts still scores confidence 1.000. The holdout is the only
    grade a generator cannot write for itself.
    """
    attempts: List[Dict[str, Any]] = []
    best: Optional[Dict[str, Any]] = None
    for i in range(1, max_retries + 1):
        print(f"  [agentic] attempt {i}/{max_retries} ...", flush=True)
        r = run_pipeline_once(objective, holdout_test=holdout_test)
        r["attempt"] = i
        gate = (
            r.get("status") == "complete"
            and r.get("sandbox_exit") == 0
            and r.get("audit_approved") is True
            and float(r.get("confidence") or 0.0) >= min_confidence
        )

        # Held-out grading, when the task supplies it. Fails closed: if the
        # holdout cannot be graded, the artifact does not pass.
        if holdout_test.strip():
            try:
                from core.holdout import grade_against_holdout

                verdict = grade_against_holdout(r.get("generated_code") or "", holdout_test)
            except Exception as e:  # noqa: BLE001 - never let this pass silently
                verdict = {"ok": False, "reason": f"holdout error: {e}"}
            r["holdout_ok"] = verdict.get("ok")
            r["holdout_reason"] = verdict.get("reason") or ""
            r["holdout_asserts"] = verdict.get("asserts")
            gate = gate and bool(verdict.get("ok"))
            print(
                f"    holdout: {'PASS' if verdict.get('ok') else 'FAIL'} "
                f"({verdict.get('asserts') or 0} unseen asserts) {verdict.get('reason') or ''}",
                flush=True,
            )
        else:
            r["holdout_ok"] = None
            r["holdout_reason"] = "no holdout for this task"

        r["gate_pass"] = gate
        attempts.append(r)
        if best is None or r["confidence"] > best["confidence"]:
            best = r
        print(
            f"  [agentic] conf={r['confidence']:.3f} ver={float(r.get('verification_score') or 0):.3f} "
            f"tests={r.get('total_tests')} audit={r['audit_approved']} "
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
    outcome = "PASS" if report["ok"] else "FAIL — audit report filed"
    pull = (report.get("steps") or {}).get("pull") or {}
    lines = [
        "# @ETHER Flywheel (rinse & repeat)",
        "",
        f"> Last cycle: **{report['timestamp']}**  ",
        f"> Result: **{outcome}**  ",
        f"> Confidence: **{g['confidence']:.3f}** (min {g['min_confidence']}) · Audit: **{g['audit_approved']}**  ",
        f"> Ver: **{g.get('verification_score', 0)}** · tests: **{g.get('total_tests', 0)}**  ",
        f"> Pull: **{'OK' if pull.get('ok') else 'FAIL'}** {pull.get('error_brief') or pull.get('healed') or ''}  ",
        f"> Report pushed: **{report.get('pushed')}** · Model: `{report.get('model', '')}`  ",
        f"> Reason: `{g.get('agentic_reason')}`",
        "",
        "## Cycle",
        "1. git pull (self-heal)",
        "2. pip reinstall editable",
        "3. daemon_smoke",
        "4. smoke + pytest + doctor",
        "5. agentic sandbox (confidence gate)",
        "6. push PASS/FAIL report to origin",
        "7. sleep → repeat",
        "",
    ]
    FLYWHEEL_MD.write_text("\n".join(lines), encoding="utf-8")


def push_report(report: Dict[str, Any], ts: str) -> bool:
    gates_pass = bool(report.get("ok"))
    conf = float(report.get("gates", {}).get("confidence") or 0.0)
    reason = report.get("gates", {}).get("agentic_reason") or "unknown"

    if not gates_pass:
        FAIL_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    for p in REPORT_PATHS:
        path = ROOT / p
        if path.exists():
            git("add", p)

    status = git("status", "--porcelain")
    if not status.get("stdout", "").strip():
        print("  [push] nothing to commit", flush=True)
        return True

    msg = (
        f"flywheel PASS conf={conf:.3f} audit=ok @ {ts}"
        if gates_pass
        else f"flywheel FAIL conf={conf:.3f} reason={reason} @ {ts} (audit review)"
    )
    commit = git("commit", "-m", msg)
    if not (commit["ok"] or commit["returncode"] == 0):
        print(f"  [push] commit failed: {(commit.get('stderr') or '')[-200:]}", flush=True)
        return False
    push = git("push", "origin", "HEAD")
    if push["ok"]:
        print(f"  [push] OK — {'PASS' if gates_pass else 'FAIL'} report sent", flush=True)
        return True
    print(f"  [push] FAILED: {(push.get('stderr') or '')[-200:]}", flush=True)
    return False


def cycle(
    do_push: bool,
    min_confidence: float,
    max_retries: int,
    objective: str,
    run_doctor: bool,
    holdout_test: str = "",
) -> Dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    HEARTBEAT_PATH.write_text(ts, encoding="utf-8")
    steps: Dict[str, Any] = {}
    py = sys.executable

    steps["pull"] = safe_pull(git)
    print_step("pull", steps["pull"])
    load_dotenv(ROOT / ".env", override=True)

    steps["reinstall"] = run([py, "-m", "pip", "install", "-e", ".[dev]", "-q"], timeout=300)
    if not steps["reinstall"]["ok"]:
        steps["reinstall"]["soft"] = True
        steps["reinstall"]["ok"] = True
    print_step("reinstall", steps["reinstall"])

    daemon_script = ROOT / "scripts" / "test_daemon_smoke.py"
    if daemon_script.exists():
        steps["daemon_smoke"] = run([py, str(daemon_script)], timeout=120)
        print_step("daemon_smoke", steps["daemon_smoke"])
    else:
        steps["daemon_smoke"] = {"ok": True, "soft": True, "duration_s": 0, "error_brief": "skipped"}
        print_step("daemon_smoke", steps["daemon_smoke"])

    steps["smoke"] = run([py, "scripts/smoke_test.py"], timeout=120)
    print_step("smoke", steps["smoke"])
    steps["pytest"] = run(
        [py, "-m", "pytest", "-q", "--tb=line"], timeout=900
    )  # suite mean ~380s on the autonomy host; 300s timed out every cycle (MEAS-002)
    print_step("pytest", steps["pytest"])
    if run_doctor:
        steps["doctor"] = run([py, "-c", "from cli.main import app; app(['doctor'])"], timeout=60)
        print_step("doctor", steps["doctor"])

    if os.getenv("ETHER_FLYWHEEL_BATCH_TICK", "1") == "1":
        bw = ROOT / "scripts" / "batch_worker.py"
        if bw.exists():
            steps["batch_tick"] = run([py, str(bw), "--limit", "1"], timeout=600)
            steps["batch_tick"]["soft"] = True
            steps["batch_tick"]["ok"] = True
            print_step("batch_tick", steps["batch_tick"])

    static_ok = (
        steps["smoke"]["ok"]
        and steps["pytest"]["ok"]
        and steps.get("daemon_smoke", {}).get("ok", True)
    )
    if not static_ok:
        agentic = {
            "ok": False,
            "reason": "static_gates_failed",
            "attempts": [],
            "final": None,
            "best": None,
        }
        print("  [agentic] skipped — static gates failed", flush=True)
    else:
        agentic = agentic_verify(
            objective,
            min_confidence=min_confidence,
            max_retries=max_retries,
            holdout_test=holdout_test,
        )

    gates_pass = static_ok and agentic["ok"]
    final = agentic.get("final") or {}
    conf = float(final.get("confidence") or 0.0)
    audit = bool(final.get("audit_approved"))
    ver = float(final.get("verification_score") or 0.0)
    tests = int(final.get("total_tests") or 0)

    learn_snap = {}
    try:
        from core.learning import BanditPolicy

        learn_snap = BanditPolicy().snapshot()
    except Exception:
        pass

    fail_streak = {}
    try:
        p = ROOT / "memory" / "learning" / "fail_streak.json"
        if p.exists():
            fail_streak = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass

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
            "verification_score": ver,
            "total_tests": tests,
            "audit_approved": audit,
            "max_retries": max_retries,
            "agentic_reason": agentic.get("reason"),
            "pull_ok": bool(steps["pull"].get("ok")),
            "pull_healed": steps["pull"].get("healed"),
        },
        "objective": objective[:200],
        "steps": {
            n: {
                "ok": d.get("ok"),
                "returncode": d.get("returncode"),
                "duration_s": d.get("duration_s"),
                "healed": d.get("healed"),
                "soft": d.get("soft"),
                "error_brief": d.get("error_brief") or "",
            }
            for n, d in steps.items()
        },
        "learning": learn_snap,
        "fail_streak": fail_streak,
        "agentic": {
            "ok": agentic["ok"],
            "reason": agentic.get("reason"),
            "attempts": [
                {
                    "attempt": a.get("attempt"),
                    "confidence": a.get("confidence"),
                    "verification_score": a.get("verification_score"),
                    "total_tests": a.get("total_tests"),
                    "audit_approved": a.get("audit_approved"),
                    "sandbox_exit": a.get("sandbox_exit"),
                    "gate_pass": a.get("gate_pass"),
                    "error": a.get("error"),
                    "stderr": (a.get("sandbox_stderr") or "")[:300],
                    "task_id": a.get("task_id"),
                    "fail_kind": a.get("fail_kind"),
                }
                for a in agentic.get("attempts", [])
            ],
        },
        "push_allowed": True if want_push else False,
        "quality_pass": gates_pass,
        "pushed": False,
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    with HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(report) + "\n")
    write_dashboard(report)

    if want_push:
        print(
            f"  [report] {'PASS' if gates_pass else 'FAIL'} — publishing report",
            flush=True,
        )
        report["pushed"] = push_report(report, ts)
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
                "quality_pass": data.get("quality_pass", data.get("ok")),
                "pushed": data.get("pushed"),
                "confidence": data.get("gates", {}).get("confidence"),
                "verification_score": data.get("gates", {}).get("verification_score"),
                "audit_approved": data.get("gates", {}).get("audit_approved"),
                "pull_ok": data.get("gates", {}).get("pull_ok"),
                "model": data.get("model"),
                "agentic_reason": data.get("gates", {}).get("agentic_reason"),
            },
            indent=2,
        )
    )
    return 0 if data.get("ok") else 1


def main(argv: Optional[List[str]] = None) -> int:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="@ETHER autonomous flywheel")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--autonomous", action="store_true")
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

    continuous = args.autonomous or args.loop > 0
    interval = args.interval if args.autonomous else (args.loop or args.interval)
    do_push = _compute_do_push(args.push)

    def once() -> int:
        # Prefer curriculum when autonomous / env says so
        objective = args.objective
        holdout_test = ""
        if continuous or os.getenv("ETHER_CURRICULUM", "1") == "1":
            try:
                from scripts.flywheel_intelligence import resolve_objective

                objective, _meta = resolve_objective(args.objective)
                holdout_test = str(_meta.get("holdout_test") or "")
            except Exception:
                pass
        report = cycle(
            do_push=do_push,
            min_confidence=args.min_confidence,
            max_retries=max(1, args.max_retries),
            objective=objective,
            run_doctor=not args.no_doctor,
            holdout_test=holdout_test,
        )
        print(
            json.dumps(
                {
                    "ok": report["ok"],
                    "quality_pass": report.get("quality_pass", report["ok"]),
                    "pushed": report.get("pushed", False),
                    "confidence": report["gates"]["confidence"],
                    "verification_score": report["gates"].get("verification_score"),
                    "total_tests": report["gates"].get("total_tests"),
                    "audit_approved": report["gates"]["audit_approved"],
                    "pull_ok": report["gates"].get("pull_ok"),
                    "agentic_reason": report["gates"].get("agentic_reason"),
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
        f"@ETHER RINSE-REPEAT on — interval={interval}s model={os.getenv('ETHER_PRIMARY_MODEL', '')}",
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
