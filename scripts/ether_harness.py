"""ETHER Harness v2 — Hermes-class terminal control plane.

Inspired by Hermes Agent (Nous Research) CLI patterns, adapted to ETHER:
  - Slash commands (/status /phase /swarm …)
  - Shell mode (!cmd) — zero LLM cost, does not enter chat history
  - Agent-default: free text → local orchestrated turn (one hypothesis)
  - Session log at artifacts/harness_session.jsonl
  - Skills list/show from apprentice lessons
  - Wave / max-swarm enqueue under training wheels
  - No FastAPI / browser. Same artifacts + operator_surface truth.

Doctrine (unchanged):
  Training wheels ON until honest_rate_eligible ≥ 0.99
  One hypothesis per chat / job
  Never auto-lift soft launch

Usage:
  .venv\\Scripts\\python.exe -m scripts.ether_harness
  .venv\\Scripts\\python.exe -m scripts.ether_harness --once /status
  .venv\\Scripts\\python.exe -m scripts.ether_harness --watch 4
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
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SESSION_PATH = ROOT / "artifacts" / "harness_session.jsonl"
SESSION_MAX_LINES = 500

BANNER = """
╔════════════════════════════════════════════════════════════════╗
║  ETHER HARNESS v2  ·  Hermes-class  ·  training wheels ON      ║
║  /status /phase /swarm /skills   !shell   free-text → agent    ║
╚════════════════════════════════════════════════════════════════╝
""".strip()

HELP = """
Hermes-class commands
─────────────────────
  Slash (type /…):
    /help /h /?              this help
    /status /st              host + GPU + queue counts
    /phase /ph               honest_rate, metrics_go, open checks
    /queue /q                pending + failed
    /rates /r                phase1 + eligible rates
    /doctor /doc             health issues
    /next                    next pending job
    /learn                   preference / strategy summary
    /llm                     multi-llm lanes
    /tools                   persistent + quarantine tools
    /mcp                     local tools + gems registry
    /skills [/list|/show id] apprentice skills
    /goal                    phase ambition board (from phase1_gate)
    /inbox                   Grok bus inbox
    /clear                   clear chat session (archive kept)
    /session                 last harness session turns
    /wave [n] [--live]       enqueue n greeter/wallet gate_samples (default n=4 live)
    /swarm [--live]          alias: wave of wallet+greeter
    /test <fixture> [--live] single measurement job
    /job list|cancel <id>
    /watch [sec]             live status strip (Ctrl+C stop)
    /quit /exit             leave harness

  Shell mode (zero LLM cost, not logged to chat):
    !git status
    !dir artifacts\\jobs\\pending
    !pytest tests/test_train_gates.py -q

  Agent mode (default):
    <any free text>          → local orchestrated turn (one hypothesis)
    chat [local|grok|status|git] <msg>   explicit channel

Doctrine: wheels ON · one hypothesis · measured rate climb only
""".strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_clock() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def _print_json(data: Any, *, max_chars: int = 4000) -> None:
    text = json.dumps(data, indent=2, default=str)
    if len(text) > max_chars:
        text = text[: max_chars - 20] + "\n… (truncated)"
    print(text)


def _session_append(kind: str, payload: Dict[str, Any]) -> None:
    try:
        SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
        rec = {"ts": _now_iso(), "kind": kind, **payload}
        with SESSION_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        # rotate soft
        if SESSION_PATH.stat().st_size > 2_000_000:
            lines = SESSION_PATH.read_text(encoding="utf-8").splitlines()
            keep = lines[-SESSION_MAX_LINES:]
            SESSION_PATH.write_text("\n".join(keep) + "\n", encoding="utf-8")
    except Exception:
        pass


def strip_status() -> str:
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
            f"[{_now_clock()}] phase={host.get('phase')} "
            f"job={host.get('current_job') or last.get('job_id') or '—'} "
            f"last={ok_s} pending={s.get('pending_n')} "
            f"rate={rate_s} wheels={'ON' if p1.get('training_wheels') else 'OFF'}"
        )
    except Exception as e:
        return f"[{_now_clock()}] harness error: {type(e).__name__}: {e}"


# ─── commands ───────────────────────────────────────────────────────────────

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
    bad = [c for c in (p1.get("checks") or []) if not c.get("ok")]
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
        for j in jobs[:30]:
            print(f"  - {j}")
        if len(jobs) > 30:
            print(f"  … +{len(jobs) - 30} more")
    return 0


def cmd_rates() -> int:
    from core.operator_surface import rates

    data = rates()
    _print_json(
        {
            "updated": data.get("updated"),
            "phase1_gate": data.get("phase1_gate"),
            "eligible_rates": data.get("eligible_rates"),
        }
    )
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
        print("next: (empty)")
        return 0
    print(f"next: {pending[0]}")
    for j in pending[1:6]:
        print(f"  then: {j}")
    return 0


def cmd_learn() -> int:
    from core.operator_surface import learn_summary

    _print_json(learn_summary(), max_chars=3500)
    return 0


def cmd_llm() -> int:
    try:
        from core.multi_llm import publish

        _print_json(publish())
    except Exception as e:
        print(f"llm error: {e}")
        return 1
    return 0


def cmd_tools() -> int:
    from core.operator_surface import tools_list

    _print_json(tools_list())
    return 0


def cmd_mcp() -> int:
    from core.operator_surface import mcp_list

    _print_json(mcp_list())
    return 0


def cmd_skills(parts: List[str]) -> int:
    from core.operator_surface import skill_list, skill_show

    if not parts or parts[0] in ("list", "ls"):
        items = skill_list()
        print(f"skills ({len(items)}):")
        for s in items:
            print(f"  - {s.get('id')}  [{s.get('craft')}]  {(s.get('rule') or '')[:80]}")
        return 0
    if parts[0] == "show" and len(parts) >= 2:
        _print_json(skill_show(parts[1]))
        return 0
    # bare id
    _print_json(skill_show(parts[0]))
    return 0


def cmd_goal() -> int:
    """Phase ambition board — measured truth only."""
    from core.operator_surface import rates

    p1 = rates().get("phase1_gate") or {}
    print("@ETHER goal board")
    print(f"  phase_gate        {p1.get('phase_gate')}")
    print(f"  status            {p1.get('status')}")
    print(f"  architecture_go   {p1.get('architecture_go')}")
    print(f"  metrics_go        {p1.get('metrics_go')}  (need honest≥0.99)")
    print(f"  honest_rate       {p1.get('honest_rate_eligible')}")
    print(f"  live_eligible_n   {p1.get('live_eligible_n')}")
    print(f"  training_wheels   {p1.get('training_wheels')}")
    print(f"  soft_launch       {p1.get('soft_launch_ready')}  (human only)")
    print("  primary: stack easy gate_sample until rate ≥ 0.99; wheels stay ON")
    return 0


def cmd_chat(parts: List[str], *, default_local: bool = False) -> int:
    from core.operator_surface import chat_post

    if not parts:
        print("usage: chat [local|grok|status|git] <message>  OR free-text for local")
        return 2

    channel: Optional[str] = None
    msg_parts = parts
    if parts[0].lower() in ("local", "grok", "status", "git", "auto"):
        channel = parts[0].lower()
        if channel == "auto":
            channel = None
        msg_parts = parts[1:]
    elif default_local:
        channel = "local"

    message = " ".join(msg_parts).strip()
    if not message:
        print("empty message")
        return 2

    result = chat_post(message, orchestrate=True, force_channel=channel)
    ok = result.get("ok", True)
    _session_append(
        "chat",
        {
            "channel": result.get("channel") or channel or "auto",
            "message": message[:500],
            "ok": ok,
            "intent": result.get("intent"),
            "reply_preview": (result.get("reply") or "")[:300],
        },
    )

    if result.get("schema") == "ether_chat_turn_v1" or "reply" in result:
        print(f"ok={ok}  intent={result.get('intent')}  channel={result.get('channel')}")
        reply = (result.get("reply") or "")[:2500]
        print(reply if reply else "(no reply body)")
        if result.get("awaiting_grok"):
            print("— awaiting Grok on bus (host will push)")
        return 0 if ok else 1

    if result.get("fallback"):
        print(f"orchestrator fallback: {result.get('error')}")
        return 1

    print(f"posted {result.get('id')}")
    return 0


def cmd_inbox(limit: int = 10) -> int:
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


def cmd_session(limit: int = 15) -> int:
    if not SESSION_PATH.exists():
        print("session: empty")
        return 0
    lines = SESSION_PATH.read_text(encoding="utf-8").splitlines()
    for line in lines[-limit:]:
        try:
            rec = json.loads(line)
        except Exception:
            continue
        ts = (rec.get("ts") or "")[:19]
        kind = rec.get("kind")
        if kind == "chat":
            print(
                f"  [{ts}] chat/{rec.get('channel')} ok={rec.get('ok')} "
                f"· {(rec.get('message') or '')[:60]}"
            )
        elif kind == "shell":
            print(f"  [{ts}] ! {rec.get('cmd')} rc={rec.get('rc')}")
        elif kind == "wave":
            print(f"  [{ts}] wave n={rec.get('n')} jobs={rec.get('jobs')}")
        else:
            print(f"  [{ts}] {kind} {json.dumps({k: v for k, v in rec.items() if k not in ('ts', 'kind')}, default=str)[:80]}")
    return 0


def cmd_test(parts: List[str]) -> int:
    from core.operator_surface import run_test

    if not parts:
        print("usage: /test <fixture> [--live]")
        return 2
    fixture = parts[0]
    live = "--live" in parts or "live" in parts
    path = run_test(
        fixture,
        live=live,
        arm="direct",
        max_steps=10 if live else 8,
        timeout=200,
    )
    print(f"enqueued {path.name}  live={live}")
    _session_append("test", {"job": path.name, "fixture": fixture, "live": live})
    return 0


def cmd_wave(parts: List[str]) -> int:
    """Enqueue n easy gate_sample jobs (greeter/wallet alternating). Under wheels."""
    from core.operator_surface import run_test

    n = 4
    live = True
    for p in parts:
        if p in ("--scripted", "scripted"):
            live = False
        elif p in ("--live", "live"):
            live = True
        else:
            try:
                n = max(1, min(int(p), 8))
            except ValueError:
                pass

    fixtures = ["greeter", "wallet"] * ((n + 1) // 2)
    fixtures = fixtures[:n]
    jobs: List[str] = []
    for fx in fixtures:
        path = run_test(fx, live=live, arm="direct", max_steps=10 if live else 8, timeout=200)
        jobs.append(path.name)
        print(f"enqueued {path.name}")
    _session_append("wave", {"n": n, "live": live, "jobs": jobs})
    print(f"wave: {n} jobs live={live} — host drains FIFO under wheels")
    return 0


def cmd_swarm(parts: List[str]) -> int:
    return cmd_wave(["4"] + parts)


def cmd_job(parts: List[str]) -> int:
    from core.operator_surface import list_jobs, cancel_job

    if not parts or parts[0] == "list":
        return cmd_queue()
    if parts[0] == "cancel" and len(parts) >= 2:
        ok = cancel_job(parts[1])
        print("cancelled" if ok else "not found")
        return 0 if ok else 1
    print("usage: /job list | /job cancel <id>")
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


def cmd_shell(cmd: str) -> int:
    """Hermes-style !shell — no LLM, not in chat history."""
    cmd = (cmd or "").strip()
    if not cmd:
        print("usage: !<shell command>")
        return 2
    # safety: block destructive root ops in harness
    low = cmd.lower()
    blocked = ("format ", "rm -rf /", "del /s /q c:\\", "shutdown", "rd /s /q c:\\")
    if any(b in low for b in blocked):
        print("blocked: destructive command refused by harness")
        return 1
    try:
        r = subprocess.run(
            cmd,
            shell=True,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        out = (r.stdout or "") + (r.stderr or "")
        if out.strip():
            print(out.rstrip()[:8000])
        print(f"[rc={r.returncode}]")
        _session_append("shell", {"cmd": cmd[:200], "rc": r.returncode})
        return 0 if r.returncode == 0 else 1
    except subprocess.TimeoutExpired:
        print("shell timeout (120s)")
        return 1
    except Exception as e:
        print(f"shell error: {e}")
        return 1


# ─── dispatch ───────────────────────────────────────────────────────────────

SLASH: Dict[str, Any] = {
    "help": lambda p: (print(HELP) or 0),
    "h": lambda p: (print(HELP) or 0),
    "?": lambda p: (print(HELP) or 0),
    "status": lambda p: cmd_status(),
    "st": lambda p: cmd_status(),
    "phase": lambda p: cmd_phase(),
    "ph": lambda p: cmd_phase(),
    "queue": lambda p: cmd_queue(),
    "q": lambda p: cmd_queue(),
    "rates": lambda p: cmd_rates(),
    "r": lambda p: cmd_rates(),
    "doctor": lambda p: cmd_doctor(),
    "doc": lambda p: cmd_doctor(),
    "next": lambda p: cmd_next(),
    "learn": lambda p: cmd_learn(),
    "llm": lambda p: cmd_llm(),
    "tools": lambda p: cmd_tools(),
    "mcp": lambda p: cmd_mcp(),
    "skills": lambda p: cmd_skills(p),
    "skill": lambda p: cmd_skills(p),
    "goal": lambda p: cmd_goal(),
    "inbox": lambda p: cmd_inbox(),
    "clear": lambda p: cmd_clear(),
    "session": lambda p: cmd_session(),
    "wave": lambda p: cmd_wave(p),
    "swarm": lambda p: cmd_swarm(p),
    "test": lambda p: cmd_test(p),
    "job": lambda p: cmd_job(p),
    "watch": lambda p: cmd_watch(float(p[0]) if p else 4.0),
    "chat": lambda p: cmd_chat(p),
    "quit": lambda p: -1,
    "exit": lambda p: -1,
}


def dispatch(line: str) -> int:
    line = (line or "").strip()
    if not line:
        return 0

    # Shell mode (Hermes !)
    if line.startswith("!"):
        return cmd_shell(line[1:])

    # Slash commands
    if line.startswith("/"):
        body = line[1:].strip()
        if not body:
            print(HELP)
            return 0
        parts = body.split()
        cmd = parts[0].lower()
        rest = parts[1:]
        if cmd in ("quit", "exit"):
            return -1
        fn = SLASH.get(cmd)
        if fn is None:
            print(f"unknown /{cmd}  — type /help")
            return 2
        try:
            return int(fn(rest))
        except ValueError:
            # watch interval parse etc.
            return int(fn([]))

    # Legacy bare commands (compat with v1)
    parts = line.split()
    cmd0 = parts[0].lower()
    if cmd0 in SLASH and cmd0 not in ("chat",):
        return int(SLASH[cmd0](parts[1:]))
    if cmd0 == "chat":
        return cmd_chat(parts[1:])
    if cmd0 in ("quit", "exit", "q!"):
        return -1
    if cmd0 in ("help", "?"):
        print(HELP)
        return 0

    # Hermes agent-default: free text → local turn (one hypothesis)
    return cmd_chat(parts, default_local=True)


def repl() -> int:
    print(BANNER)
    print(strip_status())
    print("type /help · !shell · free-text agents · /quit")
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
        description="ETHER Hermes-class terminal harness (wheels ON)",
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
