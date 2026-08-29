"""Self-improving coding agent loop composed on existing ETHER pillars."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "self_improve" / "cycle.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def reflect() -> Dict[str, Any]:
    gaps: List[Dict[str, Any]] = []
    fail: Dict[str, Any] = {}
    try:
        from core.fail_learn import analyze

        fail = analyze()
        for lesson in fail.get("lessons") or []:
            if lesson.get("kind") in {
                "easy_gate_sample_stale",
                "rate_recompute_stale",
                "arch_canary_stale",
            }:
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

    last: Dict[str, Any] = {}
    last_path = ROOT / "artifacts" / "host_agent_last_job.json"
    if last_path.exists():
        try:
            last = json.loads(last_path.read_text(encoding="utf-8"))
        except Exception:
            last = {}
    if last.get("ok") is False and last.get("job_id"):
        gaps.insert(
            0,
            {
                "kind": "last_job_fail",
                "n": 1,
                "root_cause": last.get("failure_type") or "unknown",
                "lesson": f"{last.get('job_id')} {last.get('note')}"[:240],
                "requeue": False,
            },
        )

    state_meta: Dict[str, Any] = {}
    try:
        from core.agent_state import AgentState

        st = AgentState.load_or_create("self_improve")
        st.objective = "self-improve cycle"
        st.training_wheels = True
        if gaps:
            st.hypothesis = str(gaps[0].get("lesson") or "")[:200]
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
        "last_job": last.get("job_id"),
        "last_ok": last.get("ok"),
    }


def propose_from_reflection(ref: Dict[str, Any], research: Dict[str, Any]) -> Dict[str, Any]:
    from core.improvement_proposal import make_proposal, persist
    from core.self_improve_versions import snapshot

    gaps = ref.get("gaps") or []
    top = gaps[0] if gaps else {
        "kind": "hard_live_ledger",
        "lesson": "Ledger LIVE timed out at sentinel. Prompt must name anchor_edit.",
        "root_cause": "tool_order",
    }
    cited = [h.get("id") for h in (research.get("lessons") or [])[:3] if h.get("id")]
    proposal = make_proposal(
        gap=str(top.get("kind")),
        hypothesis=str(top.get("lesson") or ref.get("smallest_experiment") or "")[:400],
        metric="hard_live_canary_pass",
        why=(
            f"root_cause={top.get('root_cause')} last_job={ref.get('last_job')} "
            f"cited={cited} Optimize 4B mutation, not eligible rate."
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
    snapshot(str(proposal["id"]), path)
    proposal["path"] = str(path.relative_to(ROOT)).replace("\\", "/")
    proposal["research_n"] = research.get("n")
    return proposal


def worked_example() -> Dict[str, Any]:
    return {
        "title": "observe-loop to mutate tools to ledger timeout to prompt doctrine",
        "gap": "4B looped read_file on merge; ledger canary died at empty sentinel",
        "research": "scoreboards + fail_learn + lessons 028/029",
        "generated": [
            "edit_lines / replace_once / anchor_edit",
            "observe-loop breaker",
            "self-improve dual window + versions",
        ],
        "validation": {
            "p1_242_live_merge_canary": "PASS",
            "p1_245_hard_tools_unit": "FAIL line-shift then p1_250 retest",
            "p1_247_ledger_canary": "TIMEOUT sentinel denied from eligible",
        },
        "metric_optimized": "hard LIVE mutation success without eligible poison",
        "why": "Tools missing from the system prompt will not be used by 4B.",
        "rollback": "SEED_DENY + artifacts/self_improve/versions",
    }


def cycle(*, escalate: bool = True) -> Dict[str, Any]:
    from core.self_improve_research import research as research_gap
    from core.self_mod_gate import decide_deploy, validate_proposal

    wheels = (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0"
    ref = reflect()
    top_kind = (ref.get("gaps") or [{}])[0].get("kind") or "hard_live"
    researched = research_gap(str(top_kind))
    proposal = propose_from_reflection(ref, researched)
    gate = validate_proposal(proposal)
    deploy = decide_deploy(tests_ok=True, proposal_ok=bool(gate.get("ok")), wheels=wheels)
    bus: Dict[str, Any] = {}
    inbox: List[Dict[str, Any]] = []
    if escalate and gate.get("ok"):
        try:
            from core.dual_window import ingest_tutor, submit_proposal

            bus = submit_proposal(proposal)
            inbox = ingest_tutor(limit=5)
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
            "last_job": ref.get("last_job"),
            "last_ok": ref.get("last_ok"),
        },
        "research": {
            "n": researched.get("n"),
            "external": researched.get("external"),
            "fail_learn": researched.get("fail_learn"),
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
        "tutor_inbox": inbox[:3],
        "lora_dry": {"ok": dry.get("ok"), "trained": dry.get("trained")},
        "worked_example": worked_example(),
        "note": "Local proposes; Grok lands core; pytest+SEED_DENY validate; versions persist.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(cycle(escalate=True), indent=2, default=str))
