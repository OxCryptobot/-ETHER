"""Optional LangGraph planning path for Selenite — self-evolving state.

Improvements (2026-08-08):
  - PlanState carries last_critique, hypothesis, root_cause, introspection
  - Persistent file checkpoint (thread_id) under artifacts/langgraph_checkpoints/
  - Interleaved introspect node that forces the four self-improvement questions
  - Conditional severity path driven by Labradorite root_cause
  - Tool-calling stubs for Clear Quartz / Grandidierite (executed later by host)
  - Still falls back cleanly if langgraph missing

This is synergistic with EvolutionController, not a full multi-agent runtime.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

from core.schemas import ExecutionPlan, PlanStep

ROOT = Path(__file__).resolve().parents[2]
CKPT_DIR = ROOT / "artifacts" / "langgraph_checkpoints"


class PlanState(TypedDict, total=False):
    query: str
    max_depth: int
    intent: str
    steps: List[Dict[str, Any]]
    reasoning: str
    # Synergistic with GEM evolution loop
    last_critique: str
    hypothesis: str
    root_cause: str
    severity: str
    introspection: str
    thread_id: str


def _classify_intent(query: str) -> str:
    q = query.lower()
    if any(w in q for w in ["refactor", "restructure", "clean up"]):
        return "refactor"
    if any(w in q for w in ["add", "implement", "create", "write", "build", "make"]):
        return "implement"
    if any(w in q for w in ["fix", "debug", "error", "bug", "broken"]):
        return "fix"
    if any(w in q for w in ["explain", "what", "how", "document"]):
        return "explain"
    if any(w in q for w in ["evolve", "improve", "self", "lora", "adapter"]):
        return "evolve"
    return "general"


def _severity(root_cause: str) -> str:
    high = {"parse_fail", "sandbox_fail", "tool_order"}
    med = {"repair_quality", "verification_fail", "budget_exhaust"}
    if root_cause in high:
        return "high"
    if root_cause in med:
        return "medium"
    return "low"


def _steps_for_intent(intent: str, max_depth: int, severity: str = "low") -> List[PlanStep]:
    catalogs = {
        "refactor": [
            PlanStep(id=1, action="analyze", target="codebase", description="Map current structure and dependencies"),
            PlanStep(id=2, action="design", target="target_structure", deps=[1], description="Design improved structure"),
            PlanStep(id=3, action="migrate", target="code", deps=[2], description="Apply refactoring changes"),
            PlanStep(id=4, action="test", target="sandbox", deps=[3], description="Verify behavior unchanged"),
            PlanStep(id=5, action="validate", target="security", deps=[4], description="Security and quality audit"),
        ],
        "implement": [
            PlanStep(id=1, action="analyze", target="codebase", description="Understand current structure"),
            PlanStep(id=2, action="generate", target="code", deps=[1], description="Generate the required code"),
            PlanStep(id=3, action="test", target="sandbox", deps=[2], description="Run in Clear Quartz sandbox"),
            PlanStep(id=4, action="validate", target="security", deps=[3], description="Security and quality check"),
        ],
        "fix": [
            PlanStep(id=1, action="reproduce", target="error", description="Reproduce the issue"),
            PlanStep(id=2, action="diagnose", target="root_cause", deps=[1], description="Find root cause (Labradorite)"),
            PlanStep(id=3, action="fix", target="code", deps=[2], description="Apply minimal fix"),
            PlanStep(id=4, action="test", target="sandbox", deps=[3], description="Verify fix in Clear Quartz"),
        ],
        "evolve": [
            PlanStep(id=1, action="introspect", target="self", description="Ask the four self-improvement questions"),
            PlanStep(id=2, action="critique", target="labradorite", deps=[1], description="Structured root_cause + smallest_experiment"),
            PlanStep(id=3, action="prepare_data", target="lora_prep", deps=[2], description="Gated preference + SFT export"),
            PlanStep(id=4, action="train_adapter", target="lora_train", deps=[3], description="Dry-run or gated adapter (wheels)"),
            PlanStep(id=5, action="remember", target="citrine", deps=[4], description="Persist adapter memory"),
        ],
        "explain": [
            PlanStep(id=1, action="retrieve", target="context", description="Gather relevant code/docs"),
            PlanStep(id=2, action="synthesize", target="explanation", deps=[1], description="Produce clear explanation"),
        ],
        "general": [
            PlanStep(id=1, action="understand", target="request", description="Parse user intent"),
            PlanStep(id=2, action="respond", target="user", deps=[1], description="Generate response"),
        ],
    }
    steps = catalogs.get(intent, catalogs["general"])[:max_depth]
    if severity == "high" and intent != "evolve":
        # Force critique early
        steps.insert(0, PlanStep(
            id=0, action="critique", target="labradorite",
            description="High severity — Labradorite first before any generation",
        ))
    return steps


def _introspect(state: PlanState) -> str:
    """The system must always ask itself these questions."""
    questions = [
        "How do we get better?",
        "How do we self-improve?",
        "How can I surpass my limitations?",
        "What do I need to do?",
    ]
    answers = []
    rc = state.get("root_cause") or "none"
    hyp = state.get("hypothesis") or "none"
    answers.append(f"1. Get better by measuring (scoreboards) → preference pairs → gated adapter only after clean data.")
    answers.append(f"2. Self-improve via Labradorite structured critique + smallest_experiment under training wheels.")
    answers.append(f"3. Surpass limitations by keeping rank small, VRAM-aware, and never unrestricted weight updates.")
    answers.append(f"4. Need to do: run lora_prep → dry_run_report → only then consider ETHER_LORA_TRAIN=1. Current root_cause={rc}, hyp={hyp[:60]}")
    return "INTROSPECTION:\n" + "\n".join(f"Q: {q}\nA: {a}" for q, a in zip(questions, answers))


def _save_checkpoint(thread_id: str, state: PlanState) -> None:
    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    path = CKPT_DIR / f"{thread_id}.json"
    # Only serializable fields
    safe = {k: v for k, v in state.items() if isinstance(v, (str, int, float, list, dict, type(None)))}
    path.write_text(json.dumps(safe, indent=2), encoding="utf-8")


def _load_checkpoint(thread_id: str) -> Dict[str, Any]:
    path = CKPT_DIR / f"{thread_id}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_plan_with_graph(
    query: str,
    max_depth: int = 5,
    last_critique: str = "",
    hypothesis: str = "",
    root_cause: str = "",
    thread_id: str = "",
) -> Optional[ExecutionPlan]:
    """Try LangGraph StateGraph with introspect + severity + checkpoint.

    Return None to signal caller to use rule planner.
    """
    try:
        from langgraph.graph import END, StateGraph
    except Exception:
        return None

    tid = thread_id or "default"
    prior = _load_checkpoint(tid)

    def classify(state: PlanState) -> PlanState:
        intent = _classify_intent(state["query"])
        sev = _severity(state.get("root_cause") or prior.get("root_cause") or "")
        reasoning = f"LangGraph intent={intent} severity={sev}"
        if state.get("root_cause") or prior.get("root_cause"):
            reasoning += f" | root_cause={state.get('root_cause') or prior.get('root_cause')}"
        if state.get("hypothesis") or prior.get("hypothesis"):
            reasoning += f" | hyp={(state.get('hypothesis') or prior.get('hypothesis') or '')[:80]}"
        return {
            **state,
            **{k: v for k, v in prior.items() if k not in state or not state.get(k)},
            "intent": intent,
            "severity": sev,
            "reasoning": reasoning,
            "thread_id": tid,
        }

    def introspect(state: PlanState) -> PlanState:
        text = _introspect(state)
        return {**state, "introspection": text, "reasoning": (state.get("reasoning") or "") + " | introspected"}

    def expand(state: PlanState) -> PlanState:
        steps = _steps_for_intent(
            state.get("intent", "general"),
            state.get("max_depth", 5),
            state.get("severity", "low"),
        )
        # Carry prior critique as review step under training wheels
        if state.get("last_critique") and len(steps) < (state.get("max_depth") or 5):
            steps.append(
                PlanStep(
                    id=len(steps) + 1,
                    action="review",
                    target="labradorite",
                    deps=[steps[-1].id] if steps else [],
                    description="Apply prior Labradorite critique; keep change minimal",
                )
            )
        # Tool stubs
        if state.get("intent") in ("fix", "implement", "evolve"):
            steps.append(
                PlanStep(
                    id=len(steps) + 1,
                    action="sandbox",
                    target="clear_quartz",
                    description="Clear Quartz verification (host will execute)",
                )
            )
        return {
            **state,
            "steps": [s.model_dump() for s in steps],
        }

    def persist(state: PlanState) -> PlanState:
        _save_checkpoint(tid, state)
        return state

    try:
        g = StateGraph(PlanState)
        g.add_node("classify", classify)
        g.add_node("introspect", introspect)
        g.add_node("expand", expand)
        g.add_node("persist", persist)
        g.set_entry_point("classify")
        g.add_edge("classify", "introspect")
        g.add_edge("introspect", "expand")
        g.add_edge("expand", "persist")
        g.add_edge("persist", END)
        app = g.compile()
        out = app.invoke(
            {
                "query": query,
                "max_depth": max_depth,
                "last_critique": (last_critique or prior.get("last_critique") or "")[:800],
                "hypothesis": (hypothesis or prior.get("hypothesis") or "")[:300],
                "root_cause": root_cause or prior.get("root_cause") or "",
                "thread_id": tid,
            }
        )
        steps = [PlanStep(**s) for s in out.get("steps", [])]
        if not steps:
            return None
        reasoning = out.get("reasoning", "LangGraph plan")
        if out.get("introspection"):
            reasoning += "\n" + out["introspection"]
        return ExecutionPlan(
            steps=steps,
            reasoning=reasoning,
        )
    except Exception:
        return None
