"""ETHER CLI parity — same contracts as dashboard / STATUS.md.

Usage:
  python -m scripts.ether_cli status
  python -m scripts.ether_cli queue
  python -m scripts.ether_cli phase
  python -m scripts.ether_cli doctor
  python -m scripts.ether_cli next
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STATUS = ROOT / "artifacts" / "host_agent_status.json"
LAST = ROOT / "artifacts" / "host_agent_last_job.json"
PENDING = ROOT / "artifacts" / "jobs" / "pending"
DONE = ROOT / "artifacts" / "jobs" / "done"
FAILED = ROOT / "artifacts" / "jobs" / "failed"
STATUS_MD = ROOT / "STATUS.md"


def _load(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _list_jobs(folder: Path) -> List[str]:
    if not folder.exists():
        return []
    return sorted(p.stem for p in folder.glob("*.json") if p.name != ".gitkeep")


def cmd_status(_: argparse.Namespace) -> int:
    st = _load(STATUS)
    last = _load(LAST)
    hb = st.get("heartbeat") or "(none)"
    age = "?"
    try:
        t = datetime.fromisoformat(str(hb).replace("Z", "+00:00"))
        age_s = (datetime.now(timezone.utc) - t).total_seconds()
        age = f"{age_s:.0f}s ago"
    except Exception:
        pass
    print("ETHER host status")
    print(f"  heartbeat : {hb} ({age})")
    print(f"  phase     : {st.get('phase')}")
    print(f"  current   : {st.get('current_job')}")
    print(f"  last_job  : {st.get('last_job')} ok={st.get('last_ok')}")
    if last:
        print(f"  last_note : {last.get('note')}")
        print(f"  last_rc   : {last.get('rc')}")
    print(f"  pending   : {len(_list_jobs(PENDING))}")
    print(f"  done      : {len(_list_jobs(DONE))}")
    print(f"  failed    : {len(_list_jobs(FAILED))}")
    return 0


def cmd_queue(_: argparse.Namespace) -> int:
    pending = _list_jobs(PENDING)
    failed = _list_jobs(FAILED)
    print(f"pending ({len(pending)}):")
    for j in pending[:30]:
        print(f"  - {j}")
    if len(pending) > 30:
        print(f"  ... +{len(pending) - 30} more")
    print(f"failed ({len(failed)}):")
    for j in failed[:20]:
        print(f"  - {j}")
    return 0


def cmd_phase(_: argparse.Namespace) -> int:
    print("Phase board (measured)")
    print("  1A Tool-first          COMPLETE")
    print("  1B AgentState          COMPLETE")
    print("  1C AST transactional   COMPLETE")
    p1d = _load(ROOT / "artifacts" / "phase1d_status.json")
    if p1d:
        print(
            f"  1D Measured lift       {p1d.get('status')} "
            f"checks={p1d.get('checks_ok')}/{p1d.get('checks_n')}"
        )
    else:
        print("  1D Measured lift       PARTIAL (scripted GREEN; live OPEN)")
    print("Soft launch             BLOCKED until live gap closed or gate policy updated")
    ps = _load(ROOT / "artifacts" / "pipeline_strangler.json")
    if ps:
        print(
            f"Pipeline strangler       {ps.get('status')} "
            f"extracts={ps.get('extracted_ok')}/{ps.get('extracted_n')} "
            f"adapter_off={ps.get('adapter_default_off')}"
        )
    if STATUS_MD.exists():
        print()
        print("STATUS.md head:")
        for line in STATUS_MD.read_text(encoding="utf-8").splitlines()[:16]:
            print(f"  {line}")
    return 0


def cmd_next(_: argparse.Namespace) -> int:
    pending = _list_jobs(PENDING)
    if pending:
        print(f"next job: {pending[0]}")
        for j in pending[1:6]:
            print(f"  then: {j}")
    else:
        print("next job: (empty — foreman.tick should refill)")
    try:
        from scripts.foreman import status as fstatus

        s = fstatus()
        print(
            f"foreman mode={s.get('mode')} cursor={s.get('cursor')} "
            f"live_skip={s.get('live_skip_remaining')}"
        )
        if s.get("last_playbook"):
            print(f"last_playbook={s.get('last_playbook')}")
    except Exception as e:
        print(f"foreman status unavailable: {e}")
    return 0


def cmd_doctor(_: argparse.Namespace) -> int:
    issues: List[str] = []
    st = _load(STATUS)
    hb = st.get("heartbeat")
    if not hb:
        issues.append("CRITICAL: no host heartbeat (host not running?)")
    else:
        try:
            t = datetime.fromisoformat(str(hb).replace("Z", "+00:00"))
            age_s = (datetime.now(timezone.utc) - t).total_seconds()
            if age_s > 120:
                issues.append(f"WARNING: heartbeat stale ({age_s:.0f}s)")
        except Exception:
            issues.append("WARNING: heartbeat unparseable")
    if not (ROOT / ".venv" / "Scripts" / "python.exe").exists() and not (
        ROOT / ".venv" / "bin" / "python"
    ).exists():
        issues.append("WARNING: .venv python not found")
    n_failed = len(_list_jobs(FAILED))
    if n_failed > 20:
        issues.append(f"WARNING: failed queue large ({n_failed}) — run archive")

    # Strangler contracts
    try:
        from core.pipeline_strangler import compute as strangler_compute

        ps = strangler_compute()
        if ps.get("extracted_ok") != ps.get("extracted_n"):
            issues.append(
                f"WARNING: strangler extracts {ps.get('extracted_ok')}/{ps.get('extracted_n')}"
            )
        if not ps.get("adapter_default_off", True):
            issues.append("WARNING: pipeline adapter flag appears ON (expected OFF)")
        if not ps.get("terminal_contract_ok", True):
            issues.append("WARNING: terminal contract failed")
    except Exception as e:
        issues.append(f"WARNING: strangler check error: {e}")

    try:
        from core.pipeline_adapter import terminal_adapter_enabled

        if terminal_adapter_enabled():
            issues.append("INFO: ETHER_PIPELINE_TERMINAL=1 (experimental path active)")
    except Exception:
        pass

    if not issues:
        print("doctor: OK")
        return 0
    print("doctor: issues")
    for i in issues:
        print(f"  - {i}")
    # INFO-only should not fail doctor hard
    hard = [x for x in issues if not x.startswith("INFO:")]
    return 1 if hard else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ether", description="ETHER operator CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="host heartbeat + last job")
    sub.add_parser("queue", help="pending + failed list")
    sub.add_parser("phase", help="Phase 1–7 board snapshot")
    sub.add_parser("next", help="what's next from queue + foreman")
    sub.add_parser("doctor", help="quick health checks")
    args = ap.parse_args(argv)
    return {
        "status": cmd_status,
        "queue": cmd_queue,
        "phase": cmd_phase,
        "next": cmd_next,
        "doctor": cmd_doctor,
    }[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
