"""ETHER Operator CLI — Control Matrix peer.

Usage:
  python -m scripts.ether_cli status
  python -m scripts.ether_cli queue
  python -m scripts.ether_cli phase
  python -m scripts.ether_cli next
  python -m scripts.ether_cli doctor
  python -m scripts.ether_cli job enqueue --file job.json
  python -m scripts.ether_cli job cancel <id>
  python -m scripts.ether_cli job list
  python -m scripts.ether_cli test <fixture> [--live] [--arm direct]
  python -m scripts.ether_cli rates
  python -m scripts.ether_cli chat "message"
  python -m scripts.ether_cli chat inbox
  python -m scripts.ether_cli git sync
  python -m scripts.ether_cli tools
  python -m scripts.ether_cli learn
  python -m scripts.ether_cli agent
  python -m scripts.ether_cli llm
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str))


def cmd_status(_: argparse.Namespace) -> int:
    from core.operator_surface import status

    s = status()
    host = s.get("host") or {}
    last = s.get("last_job") or {}
    print("ETHER host status")
    print(f"  heartbeat : {host.get('heartbeat')}")
    print(f"  phase     : {host.get('phase')}")
    print(f"  current   : {host.get('current_job')}")
    print(f"  last_job  : {last.get('job_id')} ok={last.get('ok')}")
    print(f"  pending   : {s.get('pending_n')}")
    print(f"  done      : {s.get('done_n')}")
    print(f"  failed    : {s.get('failed_n')}")
    return 0


def cmd_queue(_: argparse.Namespace) -> int:
    from core.operator_surface import list_jobs

    pending = list_jobs("pending")
    failed = list_jobs("failed")
    print(f"pending ({len(pending)}):")
    for j in pending[:40]:
        print(f"  - {j}")
    if len(pending) > 40:
        print(f"  ... +{len(pending) - 40} more")
    print(f"failed ({len(failed)}):")
    for j in failed[:20]:
        print(f"  - {j}")
    return 0


def cmd_phase(_: argparse.Namespace) -> int:
    from core.operator_surface import rates

    r = rates()
    p1 = r.get("phase1_gate") or {}
    print("Phase board (measured)")
    print(f"  status              {p1.get('status')}")
    print(f"  architecture_go     {p1.get('architecture_go')}")
    print(f"  metrics_go          {p1.get('metrics_go')}")
    print(f"  honest_rate_eligible {p1.get('honest_rate_eligible')}")
    print(f"  live_eligible_n     {p1.get('live_eligible_n')}")
    print(f"  training_wheels     {p1.get('training_wheels')}")
    return 0


def cmd_next(_: argparse.Namespace) -> int:
    from core.operator_surface import list_jobs

    pending = list_jobs("pending")
    if pending:
        print(f"next job: {pending[0]}")
        for j in pending[1:6]:
            print(f"  then: {j}")
    else:
        print("next job: (empty — foreman.tick should refill)")
    return 0


def cmd_doctor(_: argparse.Namespace) -> int:
    from core.operator_surface import doctor

    d = doctor()
    if d.get("ok") and not d.get("issues"):
        print("doctor: OK")
        return 0
    print("doctor: issues")
    for i in d.get("issues") or []:
        print(f"  - {i}")
    return 0 if d.get("ok") else 1


def cmd_job(args: argparse.Namespace) -> int:
    from core.operator_surface import enqueue_job, cancel_job, list_jobs

    if args.job_cmd == "list":
        for kind in ("pending", "failed"):
            jobs = list_jobs(kind)
            print(f"{kind} ({len(jobs)}):")
            for j in jobs[:30]:
                print(f"  - {j}")
        return 0
    if args.job_cmd == "cancel":
        ok = cancel_job(args.id)
        print("cancelled" if ok else "not found")
        return 0 if ok else 1
    if args.job_cmd == "enqueue":
        if not args.file:
            print("--file required")
            return 2
        data = json.loads(Path(args.file).read_text(encoding="utf-8"))
        path = enqueue_job(data)
        print(f"enqueued {path.name}")
        return 0
    print("unknown job subcommand")
    return 2


def cmd_test(args: argparse.Namespace) -> int:
    from core.operator_surface import run_test

    path = run_test(
        args.fixture,
        live=bool(args.live),
        arm=args.arm or "direct",
        max_steps=int(args.max_steps or 8),
        timeout=int(args.timeout or 280),
    )
    print(f"enqueued test job: {path.name}")
    return 0


def cmd_rates(_: argparse.Namespace) -> int:
    from core.operator_surface import rates

    _print_json(rates())
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    from core.operator_surface import chat_post, chat_inbox

    if args.chat_cmd == "inbox":
        items = chat_inbox(limit=int(args.limit or 10))
        _print_json(items)
        return 0
    if not args.message:
        print("message required")
        return 2
    env = chat_post(args.message, job_id=args.job_id)
    print(f"posted {env.get('id')}")
    return 0


def cmd_git(args: argparse.Namespace) -> int:
    from core.operator_surface import git_sync

    if args.git_cmd == "sync":
        r = git_sync()
        _print_json(r)
        return 0 if r.get("ok") else 1
    print("unknown git subcommand")
    return 2


def cmd_tools(_: argparse.Namespace) -> int:
    from core.operator_surface import tools_list

    _print_json(tools_list())
    return 0


def cmd_learn(_: argparse.Namespace) -> int:
    from core.operator_surface import learn_summary

    _print_json(learn_summary())
    return 0


def cmd_agent(_: argparse.Namespace) -> int:
    from core.operator_surface import status

    _print_json(status())
    return 0


def cmd_llm(_: argparse.Namespace) -> int:
    from core.multi_llm import publish

    _print_json(publish())
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ether", description="ETHER Operator CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="host heartbeat + last job")
    sub.add_parser("queue", help="pending + failed list")
    sub.add_parser("phase", help="Phase gate snapshot")
    sub.add_parser("next", help="what's next from queue")
    sub.add_parser("doctor", help="health checks")

    p_job = sub.add_parser("job", help="job enqueue / cancel / list")
    job_sub = p_job.add_subparsers(dest="job_cmd", required=True)
    je = job_sub.add_parser("enqueue")
    je.add_argument("--file", required=True)
    jc = job_sub.add_parser("cancel")
    jc.add_argument("id")
    job_sub.add_parser("list")

    p_test = sub.add_parser("test", help="enqueue fixture test (countable)")
    p_test.add_argument("fixture")
    p_test.add_argument("--live", action="store_true")
    p_test.add_argument("--arm", default="direct")
    p_test.add_argument("--max-steps", type=int, default=8)
    p_test.add_argument("--timeout", type=int, default=280)

    sub.add_parser("rates", help="phase1_gate + eligible + multi_llm")

    p_chat = sub.add_parser("chat", help="post to Grok or read inbox")
    chat_sub = p_chat.add_subparsers(dest="chat_cmd")
    chat_sub.add_parser("inbox")
    p_chat.add_argument("message", nargs="?")
    p_chat.add_argument("--job-id")
    p_chat.add_argument("--limit", type=int, default=10)

    p_git = sub.add_parser("git", help="git hygiene")
    git_sub = p_git.add_subparsers(dest="git_cmd", required=True)
    git_sub.add_parser("sync")

    sub.add_parser("tools", help="persistent + quarantine tools")
    sub.add_parser("learn", help="preference + strategy summary")
    sub.add_parser("agent", help="full agent status JSON")
    sub.add_parser("llm", help="multi-LLM lane status")

    args = ap.parse_args(argv)
    dispatch = {
        "status": cmd_status,
        "queue": cmd_queue,
        "phase": cmd_phase,
        "next": cmd_next,
        "doctor": cmd_doctor,
        "job": cmd_job,
        "test": cmd_test,
        "rates": cmd_rates,
        "chat": cmd_chat,
        "git": cmd_git,
        "tools": cmd_tools,
        "learn": cmd_learn,
        "agent": cmd_agent,
        "llm": cmd_llm,
    }
    return dispatch[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
