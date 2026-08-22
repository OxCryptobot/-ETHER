"""Chat Orchestrator — bidirectional agent front door for ETHER.

2026-08-22d: escalate uses chat_bridge (outbox + pending_grok + dirty flag).
Host pushes artifacts/chat/ so Grok can see messages on origin.
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

_ESCALATE_RE = re.compile(
    r"\b(ask\s+grok|escalate|hand\s*off\s*to\s*grok|@grok|message\s+grok|tell\s+grok)\b",
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
    low = t.lower()
    if low in ("status", "rates", "doctor", "queue", "pending"):
        return "status"
    if low.startswith("git "):
        return "git"
    return "local_llm"


def _context_snapshot() -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for name in (
        "host_agent_status",
        "host_agent_last_job",
        "phase1_gate",
        "eligible_rates",
        "agent_state_latest",
        "gpu_metrics",
    ):
        p = ROOT / "artifacts" / f"{name}.json"
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
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
        fixtures = ["greeter", "wallet"]
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
        "You may reference host status, rates, GPU, and git state from context.\n"
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


def _escalate_to_grok(
    text: str,
    *,
    job_id: Optional[str] = None,
    parent_id: Optional[str] = None,
    turn_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Route through chat_bridge so host pushes outbox to origin for Grok."""
    from core.chat_bridge import escalate

    return escalate(text, job_id=job_id, parent_id=parent_id, turn_id=turn_id)


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
    # Grok escalations already wrote outbox; don't spam inbox with "queued" noise
    if turn.get("channel") == "grok":
        return
    try:
        from core.chat_bus import envelope, send
        from core.chat_bridge import mark_dirty

        content = turn.get("reply") or ""
        env = envelope(
            from_actor="ether",
            type_="agent_reply",
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
        send(env, to_grok=False)
        mark_dirty()
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
    try:
        from core.chat_bridge import mark_dirty

        mark_dirty()
    except Exception:
        pass
    return path


def clear_turns() -> Dict[str, Any]:
    _ensure()
    n = 0
    for p in list(TURNS.glob("turn_*.json")):
        try:
            p.unlink()
            n += 1
        except OSError:
            pass
    if LATEST.exists():
        try:
            LATEST.unlink()
        except OSError:
            pass
    try:
        from core.chat_bridge import clear_pending_grok

        clear_pending_grok()
    except Exception:
        pass
    return {"ok": True, "cleared_turns": n, "updated": _now()}


def clear_chat(*, keep_archive: bool = True) -> Dict[str, Any]:
    from core.chat_bus import clear_session

    bus = clear_session(keep_archive=keep_archive)
    turns = clear_turns()
    return {
        "ok": True,
        "bus": bus,
        "turns": turns,
        "updated": _now(),
        "note": "Chat session cleared. Archive retained." if keep_archive else "Hard wipe including archive.",
    }


def turn(
    message: str,
    *,
    job_id: Optional[str] = None,
    allow_write: bool = False,
    force_channel: Optional[str] = None,
    lane: str = "fast",
) -> Dict[str, Any]:
    text = (message or "").strip()
    turn_id = f"turn_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    fc = (force_channel or "").strip().lower()
    if fc in ("grok", "escalate", "escalate_grok"):
        intent = "escalate_grok"
    elif fc in ("local", "local_llm", "ollama"):
        intent = "local_llm"
    elif fc in ("git", "status", "job"):
        intent = fc
    else:
        intent = classify_intent(text)

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
            "schema": "ether_chat_turn_v1",
        }
        _persist(out)
        return out

    tool_results: List[Dict[str, Any]] = []
    channel = intent
    reply = ""
    ok = True

    try:
        if intent == "escalate_grok":
            clean = _ESCALATE_RE.sub("", text).strip() or text
            r = _escalate_to_grok(clean, job_id=job_id, parent_id=turn_id, turn_id=turn_id)
            tool_results.append(r)
            reply = r.get("content") or "Escalated to Grok."
            channel = "grok"
            ok = bool(r.get("ok"))

        elif intent == "git":
            r = _run_git_intent(text, allow_write=allow_write)
            tool_results.append(r)
            channel = "git"
            ok = bool(r.get("ok"))
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
                reply = json.dumps(
                    {k: v for k, v in r.items() if k != "diff"}, indent=2, default=str
                )[:3000]
            if not ok:
                reply = f"git tool failed: {r.get('error') or reply}"

        elif intent == "status":
            r = _run_status_intent(text)
            tool_results.append(r)
            channel = "status"
            ok = True
            if r.get("tool") == "doctor":
                issues = r.get("issues") or []
                reply = "doctor: " + ("; ".join(issues) if issues else "OK")
            elif r.get("tool") == "rates":
                p1 = r.get("phase1_gate") or {}
                el = r.get("eligible_rates") or {}
                rate = p1.get("honest_rate_eligible", el.get("honest_rate_eligible"))
                reply = (
                    f"honest_rate_eligible={rate} · "
                    f"live_n={p1.get('live_eligible_n') or el.get('live_eligible_n')}"
                )
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
            r = _run_local_llm(text, lane=lane)
            tool_results.append(r)
            channel = "local"
            ok = bool(r.get("ok"))
            reply = r.get("content") or r.get("error") or "(empty local reply)"
            if not ok:
                reply = (
                    f"local LLM unavailable ({r.get('error')}). "
                    "Switch channel to Grok or say 'ask grok'."
                )

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
        "awaiting_grok": channel == "grok",
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
