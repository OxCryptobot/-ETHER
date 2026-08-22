"""Chat Orchestrator — bidirectional agent front door for ETHER.

Operator message → intent → tools (git / status / jobs) and/or local Ollama
→ durable turn record → optional escalate to Grok via chat_bus.

Doctrine (locked):
- Training wheels stay ON.
- One primary hypothesis per measuring turn.
- Chat never bypasses train_gates or live_budget.
- Local Ollama is primary reasoner; Grok is escalation channel.
- Git write ops require explicit allow_write.

This is the alternative control plane to the Grok chat window.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
TURNS = ROOT / "artifacts" / "chat" / "turns"
LATEST = ROOT / "artifacts" / "chat_turn_latest.json"

# Explicit escalate markers (operator can force Grok path)
_ESCALATE_RE = re.compile(
    r"\b(ask\s+grok|escalate|hand\s*off\s*to\s*grok|@grok)\b",
    re.I,
)
_GIT_RE = re.compile(
    r"\b(git\s+(status|diff|log|branch|show|commit)|what('?s| is) (the )?(diff|status|branch)|uncommitted|working tree)\b",
    re.I,
)
_STATUS_RE = re.compile(
    r"\b(host\s+status|agent\s+status|pending\s+jobs|queue|rates?|honest_rate|heartbeat|doctor)\b",
    re.I,
)
_JOB_RE = re.compile(
    r"\b(enqueue|run\s+test|gate_sample|measure\s+(wave|batch)|swarm)\b",
    re.I,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure() -> None:
    TURNS.mkdir(parents=True, exist_ok=True)


def classify_intent(text: str) -> str:
    """Rule-first intent. Deterministic under wheels; LLM refine is optional later."""
    t = (text or "").strip()
    if not t:
        return "empty"
    if _ESCALATE_RE.search(t):
        return "escalate_grok"
    if _GIT_RE.search(t):
        return "git"
    if _STATUS_RE.search(t):
        return "status"
    if _JOB_RE.search(t):
        return "job"
    # short operational commands
    low = t.lower()
    if low in ("status", "rates", "doctor", "queue", "pending"):
        return "status"
    if low.startswith("git "):
        return "git"
    return "local_llm"


def _context_snapshot() -> Dict[str, Any]:
    """Compact host context for local LLM system prompt."""
    out: Dict[str, Any] = {}
    for name in (
        "host_agent_status",
        "host_agent_last_job",
        "phase1_gate",
        "eligible_rates",
        "agent_state_latest",
    ):
        p = ROOT / "artifacts" / f"{name}.json"
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                # bound size
                raw = json.dumps(data, default=str)
                out[name] = json.loads(raw[:2500]) if len(raw) > 2500 else data
            except Exception:
                out[name] = {"error": "unreadable"}
    return out


def _run_git_intent(text: str, *, allow_write: bool = False) -> Dict[str, Any]:
    from core import chat_git_tools as gt

    low = text.lower()
    if "diff" in low:
        return gt.git_diff(staged="staged" in low or "cached" in low)
    if "log" in low or "commit history" in low or "recent commit" in low:
        return gt.git_log(n=10)
    if "branch" in low:
        return gt.git_branch()
    if "show" in low:
        return gt.git_show("HEAD")
    if "commit" in low and allow_write:
        # extract message after commit
        m = re.search(r"commit\s+['\"]?(.+?)['\"]?$", text, re.I)
        msg = (m.group(1).strip() if m else "chat orchestrator commit")[:200]
        return gt.git_commit(message=msg, allow_write=True)
    if "commit" in low and not allow_write:
        return {
            "tool": "git_commit",
            "ok": False,
            "error": "commit requires allow_write=true on the turn",
            "hint": "Resend with allow_write or run git_status first.",
        }
    return gt.git_status()


def _run_status_intent(text: str) -> Dict[str, Any]:
    from core import operator_surface as osurf

    low = (text or "").lower()
    if "doctor" in low:
        return {"tool": "doctor", **osurf.doctor()}
    if "rate" in low or "honest" in low:
        return {"tool": "rates", **osurf.rates()}
    return {"tool": "status", **osurf.status()}


def _run_job_intent(text: str) -> Dict[str, Any]:
    """Conservative: only enqueue easy gate_sample when explicitly asked under wheels."""
    from core import operator_surface as osurf

    low = text.lower()
    live = "live" in low or "gate_sample" in low or "measure" in low
    fixtures = []
    if "greeter" in low:
        fixtures.append("greeter")
    if "wallet" in low:
        fixtures.append("wallet")
    if "merge" in low:
        fixtures.append("merge")
    if not fixtures:
        fixtures = ["greeter", "wallet"]  # easy-only default
    # refuse merge-only hard path without critique signal — still allow if listed
    paths = []
    for fx in fixtures[:3]:
        try:
            p = osurf.run_test(fx, live=live, arm="direct", max_steps=10, timeout=200)
            paths.append(p.name)
        except Exception as e:
            return {"tool": "enqueue", "ok": False, "error": str(e)[:200]}
    return {
        "tool": "enqueue",
        "ok": True,
        "jobs": paths,
        "live": live,
        "fixtures": fixtures,
        "note": "enqueued under training wheels; host drains pending",
    }


def _run_local_llm(text: str, *, lane: str = "fast") -> Dict[str, Any]:
    from core.multi_llm import chat as llm_chat

    ctx = _context_snapshot()
    system = (
        "You are ETHER, a local-first agentic coding OS on the operator host.\n"
        "Training wheels are ON. Be concise, factual, and tool-aware.\n"
        "You may reference host status, rates, and git state from context.\n"
        "Never claim soft-launch is enabled. Never invent job results.\n"
        "If the operator needs Grok, say so and suggest escalate.\n"
        f"Context JSON (bounded):\n{json.dumps(ctx, default=str)[:3500]}\n"
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": text},
    ]
    result = llm_chat(messages, lane=lane, max_tokens=768, temperature=0.2)
    return {
        "tool": "local_llm",
        "ok": bool(result.get("ok")),
        "content": result.get("content") or "",
        "model": result.get("model"),
        "lane": result.get("lane"),
        "latency_ms": result.get("latency_ms"),
        "error": result.get("error"),
    }


def _escalate_to_grok(text: str, *, job_id: Optional[str] = None, parent_id: Optional[str] = None) -> Dict[str, Any]:
    from core.chat_bus import envelope, send

    env = envelope(
        from_actor="ether_orchestrator",
        type_="operator",
        payload={
            "text": text,
            "routed": "escalate_grok",
            "note": "Chat orchestrator handed this turn to Grok",
        },
        job_id=job_id,
        requires_reply=True,
        parent_id=parent_id,
    )
    path = send(env, to_grok=True)
    return {
        "tool": "escalate_grok",
        "ok": True,
        "envelope_id": env["id"],
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "content": (
            "Escalated to Grok via chat bus outbox. "
            "Continue in the Grok window or wait for inbox reply."
        ),
    }


def _bind_agent_state(text: str, intent: str, turn_id: str) -> None:
    try:
        from core.agent_state import AgentState

        state = AgentState.load_or_create("chat_main")
        state.objective = text[:500]
        state.hypothesis = f"chat_intent={intent}"
        state.meta["last_chat_turn"] = turn_id
        state.meta["chat_orchestrator"] = True
        state.training_wheels = True
        state.save()
    except Exception:
        pass


def _reply_to_inbox(turn: Dict[str, Any]) -> None:
    """Write agent reply into chat inbox so dashboard shows bidirectional flow."""
    try:
        from core.chat_bus import envelope, send

        content = turn.get("reply") or ""
        env = envelope(
            from_actor="ether",
            type_="status",
            payload={
                "text": content,
                "turn_id": turn.get("id"),
                "intent": turn.get("intent"),
                "channel": turn.get("channel"),
                "tools": [t.get("tool") for t in (turn.get("tool_results") or [])],
            },
            parent_id=turn.get("id"),
            requires_reply=False,
        )
        # inbox = Grok/ETHER → operator view
        send(env, to_grok=False)
    except Exception:
        pass


def _persist(turn: Dict[str, Any]) -> Path:
    _ensure()
    path = TURNS / f"{turn['id']}.json"
    path.write_text(json.dumps(turn, indent=2, default=str), encoding="utf-8")
    try:
        LATEST.write_text(json.dumps(turn, indent=2, default=str), encoding="utf-8")
    except Exception:
        pass
    return path


def turn(
    message: str,
    *,
    job_id: Optional[str] = None,
    allow_write: bool = False,
    force_channel: Optional[str] = None,
    lane: str = "fast",
) -> Dict[str, Any]:
    """Execute one orchestrated chat turn.

    force_channel: 'local' | 'grok' | 'status' | 'git' | 'job' to skip classify.
    allow_write: required for git_commit.
    """
    text = (message or "").strip()
    turn_id = f"turn_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    intent = force_channel or classify_intent(text)
    if intent == "empty":
        out = {
            "id": turn_id,
            "ts": _now(),
            "ok": False,
            "intent": "empty",
            "channel": "none",
            "reply": "Empty message.",
            "tool_results": [],
            "training_wheels": True,
        }
        _persist(out)
        return out

    tool_results: List[Dict[str, Any]] = []
    channel = intent
    reply = ""
    ok = True

    try:
        if intent == "escalate_grok" or force_channel == "grok":
            # strip escalate markers for cleaner payload
            clean = _ESCALATE_RE.sub("", text).strip() or text
            r = _escalate_to_grok(clean, job_id=job_id, parent_id=turn_id)
            tool_results.append(r)
            reply = r.get("content") or "Escalated."
            channel = "grok"
            ok = bool(r.get("ok"))

        elif intent == "git":
            r = _run_git_intent(text, allow_write=allow_write)
            tool_results.append(r)
            channel = "git"
            ok = bool(r.get("ok"))
            # human-readable reply
            if r.get("tool") == "git_status":
                reply = (
                    f"branch: {r.get('branch_line') or '—'}\n"
                    f"HEAD: {r.get('head') or '—'}\n"
                    f"{r.get('porcelain') or '(clean)'}"
                )
            elif r.get("tool") == "git_diff":
                reply = f"{r.get('stat') or ''}\n{r.get('diff') or '(no diff)'}"
            elif r.get("tool") == "git_log":
                reply = "\n".join(r.get("lines") or []) or "(no log)"
            elif r.get("tool") == "git_branch":
                reply = r.get("branches") or "(no branches)"
            else:
                reply = json.dumps({k: v for k, v in r.items() if k != "diff"}, indent=2, default=str)[:3000]
            if not ok:
                reply = f"git tool failed: {r.get('error') or reply}"

        elif intent == "status":
            r = _run_status_intent(text)
            tool_results.append(r)
            channel = "status"
            ok = True
            # compact status reply
            if r.get("tool") == "doctor":
                issues = r.get("issues") or []
                reply = "doctor: " + ("; ".join(issues) if issues else "OK")
            elif r.get("tool") == "rates":
                p1 = r.get("phase1_gate") or {}
                el = r.get("eligible_rates") or {}
                rate = p1.get("honest_rate_eligible", el.get("honest_rate_eligible"))
                reply = f"honest_rate_eligible={rate} · live_n={p1.get('live_eligible_n') or el.get('live_eligible_n')}"
            else:
                host = r.get("host") or {}
                last = r.get("last_job") or {}
                reply = (
                    f"phase={host.get('phase')} · pending={r.get('pending_n')} · "
                    f"last={last.get('job_id') or host.get('current_job')} "
                    f"ok={last.get('ok')}"
                )

        elif intent == "job":
            r = _run_job_intent(text)
            tool_results.append(r)
            channel = "job"
            ok = bool(r.get("ok"))
            reply = (
                f"enqueued: {', '.join(r.get('jobs') or [])}"
                if ok
                else f"enqueue failed: {r.get('error')}"
            )

        else:
            # local_llm default
            r = _run_local_llm(text, lane=lane)
            tool_results.append(r)
            channel = "local"
            ok = bool(r.get("ok"))
            reply = r.get("content") or r.get("error") or "(empty local reply)"
            if not ok:
                # soft-fallback: still post to bus so operator sees something
                reply = f"local LLM unavailable ({r.get('error')}). Say 'ask grok' to escalate."

    except Exception as e:
        ok = False
        reply = f"orchestrator error: {type(e).__name__}: {e}"
        tool_results.append({"tool": "_error", "ok": False, "error": str(e)[:300]})

    turn_rec: Dict[str, Any] = {
        "id": turn_id,
        "ts": _now(),
        "ok": ok,
        "intent": intent,
        "channel": channel,
        "message": text[:2000],
        "reply": (reply or "")[:8000],
        "tool_results": tool_results,
        "job_id": job_id,
        "allow_write": bool(allow_write),
        "training_wheels": True,
        "schema": "ether_chat_turn_v1",
    }
    _bind_agent_state(text, intent, turn_id)
    _persist(turn_rec)
    _reply_to_inbox(turn_rec)
    return turn_rec


def recent_turns(limit: int = 20) -> List[Dict[str, Any]]:
    _ensure()
    items: List[Dict[str, Any]] = []
    for p in sorted(TURNS.glob("turn_*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            items.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
        if len(items) >= limit:
            break
    return items


def latest_turn() -> Optional[Dict[str, Any]]:
    if LATEST.exists():
        try:
            return json.loads(LATEST.read_text(encoding="utf-8"))
        except Exception:
            pass
    turns = recent_turns(1)
    return turns[0] if turns else None


if __name__ == "__main__":
    import sys

    msg = " ".join(sys.argv[1:]) or "status"
    print(json.dumps(turn(msg), indent=2, default=str))
