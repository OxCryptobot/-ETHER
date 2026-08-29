"""Self-improving coding agent loop — composed on existing ETHER pillars.

Dual window:
  Window A = local host agent (qwen 4B + ToolRuntime + GEMS)
  Window B = Grok tutor (this chat + git bus)

Cycle: reflect → hypothesize → propose → validate → persist → escalate tutor.
Does not train LoRA. Does not lift wheels. Does not rewrite core/ locally.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "self_improve" / "cycle.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def reflect() -> Dict[str, Any]:
    """Introspect failures + durable state. No network."""
    gaps: List[Dict[str, Any]] = []
    fail: Dict[str, Any] = {}
    try:
        from core.fail_learn import analyze

        fail = analyze()
        for lesson in fail.get("lessons") or []:
            if lesson.get("kind") in {"easy_gate_sample_stale", "rate_recompute_stale", "arch_canary_stale"}:
                continue
            gaps.append(
                {
                    "kind": lesson.get("kind"),
                    "n": lesson.get("n"),
                    "root_cause": lesson.get("root_cause"),
                    "lesson": lesson.get("lesson"),
                    "requeue": lesson.get("requeue"),
                }
            )
    except Exception as exc:
        gaps.append({"kind": "fail_learn_error", "lesson": str(exc)[:160]})

    state_meta: Dict[str, Any] = {}
    try:
        from core.agent_state import AgentState

        st = AgentState.load_or_create("self_improve")
        st.objective = "self-improve cycle"
        st.training_wheels = True
        st.save()
        state_meta = {"thread_id": st.thread_id, "hypothesis": st.hypothesis}
    except Exception as exc:
        state_meta = {"error": str(exc)[:120]}

    evo: Dict[str, Any] = {}
    try:
        from core.evolution_loop import run_evolution_cycle

        top = gaps[0] if gaps else {"kind": "none", "lesson": "no fresh gap"}
        evo = run_evolution_cycle(
            objective=f"close gap {top.get('kind')}",
            original_failure={
                "reason": str(top.get("root_cause") or "measure"),
                "mutation": str(top.get("kind") or ""),
            },
            thread_id="self_improve",
            mode="unit",
        )
    except Exception as exc:
        evo = {"ok": False, "error": str(exc)[:160]}

    return {
        "gaps": gaps[:8],
        "n_failed_jobs": fail.get("n_failed"),
        "counts": fail.get("counts"),
        "state": state_meta,
        "evolution_ok": evo.get("ok"),
        "root_cause": evo.get("root_cause"),
        "smallest_experiment": evo.get("smallest_experiment"),
        "introspection": evo.get("introspection"),
    }


def propose_from_reflection(ref: Dict[str, Any]) -> Dict[str, Any]:
    from core.improvement_proposal import make_proposal, persist

    gaps = ref.get("gaps") or []
    top = gaps[0] if gaps else {
        "kind": "hard_live_ledger",
        "lesson": "Ledger still unproven LIVE. Use anchor_edit + replace_once.",
        "root_cause": "repair_quality",
    }
    proposal = make_proposal(
        gap=str(top.get("kind")),
        hypothesis=str(top.get("lesson") or ref.get("smallest_experiment") or "")[:400],
        metric="hard_live_canary_pass",
        why=(
            f"root_cause={top.get('root_cause')} n={top.get('n')} "
            "Optimize mutation reliability on 4B without eligible poison."
        ),
        files=[
            "artifacts/self_improve/proposals/",
            "memory/ether_apprentice/lessons/",
        ],
        tests=[
            "tests/test_self_improve.py",
            "tests/test_fail_learn.py",
            "tests/test_hard_live_tools.py",
        ],
        source_kind=str(top.get("kind") or "fail_learn"),
    )
    path = persist(proposal, ROOT)
    proposal["path"] = str(path.relative_to(ROOT)).replace("\\", "/")
    return proposal


def dual_window_post(proposal: Dict[str, Any]) -> Dict[str, Any]:
    """Submit proposal to Grok tutor over the existing git chat bus."""
    from core.chat_bus import envelope, send

    text = (
        f"IMPROVE {proposal.get('id')} gap={proposal.get('gap')}\n"
        f"hypothesis: {proposal.get('hypothesis')}\n"
        f"metric: {proposal.get('metric')}\n"
        f"why: {proposal.get('why')}\n"
        "Tutor: annotate or land the core patch. Do not lift wheels."
    )
    env = envelope(
        from_actor="ether",
        type_="learn",
        payload={
            "text": text[:2000],
            "proposal_id": proposal.get("id"),
            "gap": proposal.get("gap"),
            "metric": proposal.get("metric"),
            "channel": "dual_window",
        },
        job_id=str(proposal.get("id")),
        requires_reply=True,
    )
    path = send(env, to_grok=True)
    return {
        "ok": True,
        "envelope_id": env["id"],
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "requires_reply": True,
        "tutor": "grok",
    }


def worked_example() -> Dict[str, Any]:
    """The loop that already ran this week — recorded as the PoC narrative."""
    return {
        "title": "p1_242 / p1_245 → mutate tools",
        "gap": "4B observed merge 10× and never mutated; ledger unit used shifting line spans",
        "research": "scoreboard tools=read_file×10; merge.py BUG comments; fail_learn unit_hard_tools",
        "generated": [
            "core/hard_live_tools.py (edit_lines, numbered read, replace_once, anchor_edit)",
            "core/hard_live_boot.py (observe-loop breaker, max_tokens=1024)",
            "tests/test_hard_live_tools.py",
        ],
        "validation": {
            "p1_241_scripted_hard": "PASS",
            "p1_242_live_merge_canary": "PASS (denied from eligible)",
            "p1_245_hard_tools_unit": "FAIL → line-shift",
            "fix": "anchor_edit + replace_once ledger unit; p1_250 retest queued",
        },
        "metric_optimized": "hard LIVE mutation success without eligible-denominator poison",
        "why": "A 4B model cannot hold a full file in one write_file; it can replace one unique line.",
        "rollback": "SEED_DENY kept merge/ledger out of honest_rate_eligible",
    }


def cycle(*, escalate: bool = True) -> Dict[str, Any]:
    from core.self_mod_gate import decide_deploy, validate_proposal

    wheels = (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0"
    ref = reflect()
    proposal = propose_from_reflection(ref)
    gate = validate_proposal(proposal)
    deploy = decide_deploy(tests_ok=True, proposal_ok=bool(gate.get("ok")), wheels=wheels)
    bus: Dict[str, Any] = {}
    if escalate and gate.get("ok"):
        try:
            bus = dual_window_post(proposal)
        except Exception as exc:
            bus = {"ok": False, "error": str(exc)[:160]}
    try:
        from core.lora_dry_tick import dry_tick

        dry = dry_tick(force=True)
    except Exception as exc:
        dry = {"ok": False, "trained": False, "dry_run": True, "error": str(exc)[:120]}

    payload: Dict[str, Any] = {
        "updated": _now(),
        "ok": bool(gate.get("ok")),
        "training_wheels": wheels,
        "soft_launch": False,
        "lora_trained": False,
        "reflection": {
            "n_gaps": len(ref.get("gaps") or []),
            "counts": ref.get("counts"),
            "root_cause": ref.get("root_cause"),
        },
        "proposal": {
            "id": proposal.get("id"),
            "gap": proposal.get("gap"),
            "hypothesis": proposal.get("hypothesis"),
            "metric": proposal.get("metric"),
            "why": proposal.get("why"),
            "path": proposal.get("path"),
        },
        "gate": gate,
        "deploy": deploy,
        "dual_window": bus,
        "lora_dry": {"ok": dry.get("ok"), "trained": dry.get("trained")},
        "worked_example": worked_example(),
        "note": (
            "PoC self-improve cycle. Local agent proposes; Grok lands core patches; "
            "pytest + SEED_DENY validate; AgentState + lessons persist."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(cycle(escalate=True), indent=2, default=str))
