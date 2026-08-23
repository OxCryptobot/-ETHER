"""ETHER Harness — stable terminal control plane (peer to dashboard).

Design rules (2026-08-23):
  - No FastAPI / browser dependency. Reads the same artifacts host_agent writes.
  - All actions go through core.operator_surface (single facade).
  - Training wheels ON. One hypothesis per chat / job message.
  - Explicit channel control for chat (local | grok | status | git | auto).
  - Dashboard remains optional; this is the durable operator path.

Usage:
  .venv\\Scripts\\python.exe -m scripts.ether_harness
  .venv\\Scripts\\python.exe -m scripts.ether_harness --once status
  .venv\\Scripts\\python.exe -m scripts.ether_harness --watch 5
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BANNER = """
╔══════════════════════════════════════════════════════════╗
║  ETHER HARNESS  ·  terminal control plane  ·  wheels ON  ║
║  status · phase · queue · rates · doctor · chat · swarm  ║
╚══════════════════════════════════════════════════════════╝
""".strip()

HELP = """
Commands (type and Enter):
  status | st          host heartbeat, phase, last job, queue counts
  phase  | ph          honest_rate_eligible, metrics_go, wheels
  queue  | q           pending + failed (top)
  rates  | r           full rates JSON (compact)
  doctor | doc         health issues
  next                 next pending job id
  learn                preference / strategy summary
  llm                  multi-llm lanes

  chat <msg>           orchestrate (auto channel)
  chat local <msg>     force local LLM
  chat grok  <msg>     force escalate to Grok (bus)
  chat status <msg>    force status intent
  chat git <msg>       force git intent
  inbox                recent grok inbox envelopes
  clear                clear chat session (archive retained)

  test <fixture> [--live]   enqueue gate_sample / scripted test
  swarm [--live]            enqueue wallet+greeter wave
  job list | job cancel <id>

  watch [N]            live status strip every N seconds (default 4)
  help | ?             this help
  quit | exit | q!     leave harness
""".strip()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def _print_json(data: Any, *, max_chars: int = 4000) -> None:
    text = json.dumps(data, indent=2, default=str)
    if len(text) > max_chars:
        text = text[: max_chars - 20] + "\n… (truncated)"
    print(text)


def strip_status() -> str:
    """One-line status for watch / prompt."""
    try:
        from core.operator_surface import status, rates

        s = status()
        host = s.get("host") or {}
        last = s.get("last_job") or {}
        p1 = (rates().get("phase1_gate") or {})
        rate = p1.get("honest_rate_eligible")
        rate_s = f"{rate:.4f}" if isinstance(rate, (int, float)) else str(rate)
        ok = last.get("ok")
        ok_s = "PASS" if ok is True else ("FAIL" if ok is False else "—")
        return (
            f"[{_now()}] phase={host.get('phase')} "
            f"job={host.get('current_job') or last.get('job_id') or '—'} "
            f"last={ok_s} "
            f"pending={s.get('pending_n')} "
            f"rate={rate_s} "
            f"wheels={'ON' if p1.get('training_wheels') else 'OFF'}"
        )
    except Exception as e:
        return f"[{_now()}] harness status error: {type(e).__name__}: {e}"


def cmd_status() -> int:
    from core.operator_surface import status

    s = status()
    host = s.get("host") or {}
    last = s.get("last_job") or {}
    gpu = host.get("gpu") or {}
    print("ETHER host")
    print(f"  heartbeat : {host.get('heartbeat')}")
    print(f"  phase     : {host.get('phase')}")
    print(f"  current   : {host.get('current_job')}")
    print(f"  last_job  : {last.get('job_id')}  ok={last.get('ok')}  rc={last.get('rc')}")
    print(f"  pending   : {s.get('pending_n')}  done={s.get('done_n')}  failed={s.get('failed_n')}")
    if gpu:
        print(
            f"  gpu       : {gpu.get('name')}  util={gpu.get('util_gpu_pct')}%  "
            f"mem={gpu.get('mem_used_mb')}/{gpu.get('mem_total_mb')}MB  temp={gpu.get('temp_c')}C"
        )
    return 0


def cmd_phase() -> int:
    from core.operator_surface import rates

    p1 = rates().get("phase1_gate") or {}
    print("Phase board (measured)")
    print(f"  status               {p1.get('status')}")
    print(f"  architecture_go      {p1.get('architecture_go')}")
    print(f"  metrics_go           {p1.get('metrics_go')}")
    print(f"  honest_rate_eligible {p1.get('honest_rate_eligible')}")
    print(f"  live_eligible_n      {p1.get('live_eligible_n')}")
    print(f"  timeout_rate_elig    {p1.get('timeout_rate_eligible')}")
    print(f"  training_wheels      {p1.get('training_wheels')}")
    print(f"  soft_launch_ready    {p1.get('soft_launch_ready')}")
    checks = p1.get("checks") or []
    bad = [c for c in checks if not c.get("ok")]
    if bad:
        print("  open checks:")
        for c in bad:
            print(f"    - {c.get('id')}: {c.get('detail')}")
    return 0


def cmd_queue() -> int:
    from core.operator_surface import list_jobs

    for kind in ("pending", "failed"):
        jobs = list_jobs(kind)
        print(f"{kind} ({len(jobs)}):")
        for j in jobs[:25]:
            print(f"  - {j}")
        if len(jobs) > 25:
            print(f"  … +{len(jobs) - 25} more")
    return 0


def cmd_rates() -> int:
    from core.operator_surface import rates

    data = rates()
    # compact: phase1 + eligible only by default
    compact = {
        "updated": data.get("updated"),
        "phase1_gate": data.get("phase1_gate"),
        "eligible_rates": data.get("eligible_rates"),
    }
    _print_json(compact)
    return 0


def cmd_doctor() -> int:
    from core.operator_surface import doctor

    d = doctor()
    if d.get("ok") and not d.get("issues"):
        print("doctor: OK")
        return 0
    print("doctor:")
    for i in d.get("issues") or []:
        print(f"  - {i}")
    return 0 if d.get("ok") else 1


def cmd_next() -> int:
    from core.operator_surface import list_jobs

    pending = list_jobs("pending")
    if not pending:
        print("next: (empty — host idle / foreman may refill)")
        return 0
    print(f"next: {pending[0]}")
    for j in pending[1:5]:
        print(f"  then: {j}")
    return 0


def cmd_learn() -> int:
    from core.operator_surface import learn_summary

    _print_json(learn_summary(), max_chars=3000)
    return 0


def cmd_llm() -> int:
    try:
        from core.multi_llm import publish

        _print_json(publish())
    except Exception as e:
        print(f"llm error: {e}")
        return 1
    return 0


def cmd_chat(parts: List[str]) -> int:
    """chat [channel] message…"""
    from core.operator_surface import chat_post

    if not parts:
        print("usage: chat [local|grok|status|git|auto] <message>")
        return 2

    channel: Optional[str] = None
    msg_parts = parts
    if parts[0].lower() in ("local", "grok", "status", "git", "auto"):
        channel = parts[0].lower()
        if channel == "auto":
            channel = None
        msg_parts = parts[1:]
    message = " ".join(msg_parts).strip()
    if not message:
        print("empty message")
        return 2

    force = channel  # local | grok | status | git | None
    result = chat_post(message, orchestrate=True, force_channel=force)

    # normalize display
    ok = result.get("ok", True)
    if result.get("schema") == "ether_chat_turn_v1" or "reply" in result:
        print(f"ok={ok}  intent={result.get('intent')}  channel={result.get('channel')}")
        reply = (result.get("reply") or "")[:2000]
        print(reply if reply else "(no reply body)")
        if result.get("awaiting_grok"):
            print("— awaiting Grok on bus (pending set; host will push)")
        return 0 if ok else 1

    if result.get("fallback"):
        print(f"orchestrator fallback: {result.get('error')}")
        print(f"envelope: {result.get('envelope', {}).get('id')}")
        return 1

    print(f"posted envelope {result.get('id')}")
    return 0


def cmd_inbox(limit: int = 8) -> int:
    from core.operator_surface import chat_inbox

    items = chat_inbox(limit=limit)
    if not items:
        print("inbox: empty")
        return 0
    for env in items:
        ts = (env.get("ts") or "")[:19]
        payload = env.get("payload") or {}
        text = (payload.get("text") or "")[:160]
        print(f"  [{ts}] {env.get('from')} · {env.get('type')} · {text}")
    return 0


def cmd_clear() -> int:
    from core.operator_surface import chat_clear

    out = chat_clear(keep_archive=True)
    print(f"cleared: ok={out.get('ok')}  {out.get('note') or ''}")
    return 0 if out.get("ok") else 1


def cmd_test(parts: List[str]) -> int:
    from core.operator_surface import run_test

    if not parts:
        print("usage: test <fixture> [--live]")
        return 2
    fixture = parts[0]
    live = "--live" in parts or "live" in parts
    path = run_test(fixture, live=live, arm="direct", max_steps=10 if live else 8, timeout=200)
    print(f"enqueued {path.name}  live={live}")
    return 0


def cmd_swarm(parts: List[str]) -> int:
    from core.operator_surface import swarm_enqueue

    live = "--live" in parts or "live" in parts
    paths = swarm_enqueue(live=live, fixtures=["wallet", "greeter"])
    for p in paths:
        print(f"enqueued {p.name}")
    return 0


def cmd_job(parts: List[str]) -> int:
    from core.operator_surface import list_jobs, cancel_job

    if not parts or parts[0] == "list":
        return cmd_queue()
    if parts[0] == "cancel" and len(parts) >= 2:
        ok = cancel_job(parts[1])
        print("cancelled" if ok else "not found")
        return 0 if ok else 1
    print("usage: job list | job cancel <id>")
    return 2


def cmd_watch(interval: float = 4.0) -> int:
    print(f"watch every {interval}s — Ctrl+C to stop")
    try:
        while True:
            print(strip_status())
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nwatch stopped")
    return 0


def dispatch(line: str) -> int:
    line = (line or "").strip()
    if not line:
        return 0
    parts = line.split()
    cmd = parts[0].lower()
    rest = parts[1:]

    if cmd in ("help", "?", "h"):
        print(HELP)
        return 0
    if cmd in ("quit", "exit", "q!"):
        return -1
    if cmd in ("status", "st"):
        return cmd_status()
    if cmd in ("phase", "ph"):
        return cmd_phase()
    if cmd in ("queue", "q"):
        return cmd_queue()
    if cmd in ("rates", "r"):
        return cmd_rates()
    if cmd in ("doctor", "doc"):
        return cmd_doctor()
    if cmd == "next":
        return cmd_next()
    if cmd == "learn":
        return cmd_learn()
    if cmd == "llm":
        return cmd_llm()
    if cmd == "chat":
        return cmd_chat(rest)
    if cmd == "inbox":
        return cmd_inbox()
    if cmd == "clear":
        return cmd_clear()
    if cmd == "test":
        return cmd_test(rest)
    if cmd == "swarm":
        return cmd_swarm(rest)
    if cmd == "job":
        return cmd_job(rest)
    if cmd == "watch":
        interval = 4.0
        if rest:
            try:
                interval = float(rest[0])
            except ValueError:
                pass
        return cmd_watch(interval)

    print(f"unknown: {cmd}  (type help)")
    return 2


def repl() -> int:
    print(BANNER)
    print(strip_status())
    print("type help · quit to exit")
    while True:
        try:
            line = input("ether> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        code = dispatch(line)
        if code == -1:
            break
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="ether-harness",
        description="ETHER stable terminal harness (no dashboard required)",
    )
    ap.add_argument("--once", nargs=argparse.REMAINDER, help="run one command then exit")
    ap.add_argument("--watch", type=float, metavar="SEC", help="live status strip")
    args = ap.parse_args(argv)

    if args.watch is not None:
        return cmd_watch(args.watch if args.watch > 0 else 4.0)
    if args.once is not None:
        line = " ".join(args.once).strip()
        if not line:
            print("--once requires a command")
            return 2
        code = dispatch(line)
        return 0 if code in (0, -1) else code
    return repl()


if __name__ == "__main__":
    raise SystemExit(main())
