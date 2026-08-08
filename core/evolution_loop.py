"""ETHER Evolution Loop — gems as agentic units (separate or one).

This is the executable infinity topology.

GEMS can be invoked independently (host jobs, CLI, tests) or as a single
coordinated unit via EvolutionController.run_cycle().

Hard rules:
- Labradorite is mandatory on every non-infra FAIL under training wheels.
- train_gates still gate every experience / preference write.
- One hypothesis per cycle when training_wheels=True.
- No LoRA weight updates here — only clean data + structured critique +
  mandatory self-improvement introspection.
- The system ALWAYS asks itself the four questions before proposing change.
- AgentState is the durable shared state across all gems.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
CRITIQUE_DIR = ARTIFACTS / "critiques"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _self_improve_questions(context: Dict[str, Any]) -> Dict[str, Any]:
    """Mandatory. The system must never skip this."""
    rc = context.get("root_cause") or "none"
    hyp = context.get("hypothesis") or "none"
    return {
        "questions": [
            "How do we get better?",
            "How do we self-improve?",
            "How can I surpass my limitations?",
            "What do I need to do?",
        ],
        "answers": [
            "By measuring real outcomes (scoreboards) → offline preference pairs → gated LoRA only after clean data and promote flag.",
            "Via Labradorite structured root_cause + smallest_experiment, one hypothesis under training wheels, then Citrine memory of the lesson.",
            "Keep adapters tiny (rank 8–16), VRAM-aware on 4GB, never unrestricted self-modification, always dry-run first.",
            f"Run lora_prep if needed, call lora_train dry_run, only set ETHER_LORA_TRAIN=1 + ETHER_LORA_PROMOTE=1 after dashboard green. Current root_cause={rc}, hypothesis={str(hyp)[:80]}",
        ],
        "rule": "Never unrestricted self-modification. Creative discovery stays inside the gates.",
    }


class EvolutionController:
    """Orchestrates the 8-gem closed loop.

    Modes:
      - "unit": run all gems in sequence as one evolution cycle
      - "separate": return the plan for host jobs / external runners to execute
                    each gem as an independent agentic task
    """

    def __init__(self, registry=None, training_wheels: bool = True):
        if registry is None:
            from core.registry import build_default_registry
            registry = build_default_registry()
        self.registry = registry
        self.training_wheels = training_wheels or os.getenv("ETHER_TRAINING_WHEELS", "1") == "1"

    def run_cycle(
        self,
        *,
        objective: str,
        code: str = "",
        sandbox_result: Optional[Dict[str, Any]] = None,
        original_failure: Optional[Dict[str, Any]] = None,
        mode: str = "unit",
        task_id: str = "",
        thread_id: str = "",
    ) -> Dict[str, Any]:
        """One full evolution cycle.

        Returns a structured report that is also written to
        artifacts/evolution_<id>.json and (on FAIL) artifacts/critiques/.
        AgentState is loaded/saved so state survives across host restarts.
        """
        tid = task_id or str(uuid4())

        # Durable shared state
        try:
            from core.agent_state import AgentState
            state = AgentState.load_or_create(thread_id or tid[:12])
            state.objective = (objective or "")[:500]
            state.training_wheels = self.training_wheels
            if original_failure:
                state.root_cause = str(original_failure.get("reason") or original_failure.get("error") or "")[:200]
            state.save()
        except Exception:
            state = None

        report: Dict[str, Any] = {
            "id": tid,
            "timestamp": _now(),
            "objective": (objective or "")[:500],
            "mode": mode,
            "training_wheels": self.training_wheels,
            "stages": [],
            "ok": False,
            "root_cause": None,
            "smallest_experiment": None,
            "critique_path": None,
            "introspection": None,
            "thread_id": getattr(state, "thread_id", None) if state else None,
        }

        # --- 0. Mandatory self-improvement questions (always) ---
        intro = _self_improve_questions({"root_cause": None, "hypothesis": None})
        report["introspection"] = intro
        report["stages"].append({"gem": "self", "ok": True, "introspection": intro})

        # --- 1. Selenite (plan / hypothesis) ---
        plan_out = self._selenite(objective, original_failure)
        report["stages"].append({"gem": "selenite", **plan_out})
        hypothesis = plan_out.get("hypothesis") or plan_out.get("reasoning") or ""
        if state is not None:
            state.hypothesis = hypothesis[:300]
            state.save()

        # --- 2. Labradorite (mandatory on FAIL paths) ---
        must_critique = bool(original_failure) or not (sandbox_result or {}).get("ok", True)
        if must_critique or os.getenv("ETHER_FORCE_CRITIQUE", "0") == "1":
            crit = self._labradorite(code, sandbox_result, original_failure, objective, tid)
            report["stages"].append({"gem": "labradorite", **crit})
            report["root_cause"] = crit.get("root_cause")
            report["smallest_experiment"] = crit.get("smallest_experiment")
            report["critique_path"] = crit.get("path")
            # Re-answer questions with real context
            report["introspection"] = _self_improve_questions({
                "root_cause": report["root_cause"],
                "hypothesis": hypothesis,
            })
            if state is not None:
                state.root_cause = report["root_cause"]
                state.last_critique = str(crit.get("critique") or "")[:400]
                state.introspection = report["introspection"]
                state.save()
            try:
                from core.memory_bus import record_critique
                record_critique(
                    objective=objective,
                    code=code or "",
                    critique=crit.get("critique") or "",
                    suggestions=crit.get("suggested_improvements") or [],
                    complexity_score=float(crit.get("complexity_score") or 0),
                    success=False,
                    confidence=float(crit.get("confidence") or 0),
                    strategy=(original_failure or {}).get("strategy") or "",
                    task_id=tid,
                )
            except Exception as e:
                report["stages"].append({"gem": "memory_bus", "ok": False, "error": str(e)[:160]})
        else:
            report["stages"].append({"gem": "labradorite", "skipped": True, "reason": "no_failure_context"})

        # --- 3. Optional LoRA readiness signal (never trains here) ---
        try:
            from core.lora_train import dry_run_report
            lora_ready = dry_run_report()
            report["stages"].append({"gem": "lora_train", "ok": True, "dry_run": lora_ready})
        except Exception as e:
            report["stages"].append({"gem": "lora_train", "ok": False, "error": str(e)[:160]})

        # --- 4. Amethyst signal ---
        try:
            from core.schemas import Envelope, AmethystRequest
            self.registry.execute(
                Envelope(
                    task_id=uuid4(),
                    target_gem="amethyst",
                    payload=AmethystRequest(
                        action="log",
                        interaction={
                            "task_id": tid,
                            "objective": objective[:300],
                            "status": "evolution_cycle",
                            "root_cause": report.get("root_cause"),
                            "training_wheels": self.training_wheels,
                            "introspection": True,
                            "learn": False,
                        },
                    ),
                )
            )
            report["stages"].append({"gem": "amethyst", "ok": True})
        except Exception as e:
            report["stages"].append({"gem": "amethyst", "ok": False, "error": str(e)[:160]})

        # --- 5. Preference / strategy signal (offline RLHF path) ---
        try:
            from core.preference import preference_summary, _mirror_observability
            summary = preference_summary()
            _mirror_observability()
            report["preference_summary"] = {
                "n_preferences": summary.get("n_preferences"),
                "n_episodes": summary.get("n_episodes"),
                "ranked_boosts": (summary.get("ranked_boosts") or [])[:5],
            }
            report["stages"].append({"gem": "preference", "ok": True})
        except Exception as e:
            report["stages"].append({"gem": "preference", "ok": False, "error": str(e)[:160]})

        report["ok"] = True
        out_path = ARTIFACTS / f"evolution_{tid[:8]}.json"
        _write_json(out_path, report)
        report["evolution_path"] = str(out_path.relative_to(ROOT))

        if state is not None:
            state.meta["last_evolution_id"] = tid
            state.meta["last_evolution_ok"] = True
            state.save()

        return report

    def _selenite(self, objective: str, original_failure: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        try:
            from core.schemas import Envelope, SeleniteRequest
            from core.memory_bus import recent_lessons
            lessons = recent_lessons(objective, k=5)
            ctx = []
            if lessons:
                ctx.append({"kind": "lesson", "text": lessons})
            if original_failure:
                ctx.append({"kind": "critique_loop", "text": json.dumps(original_failure)[:800]})
            res = self.registry.execute(
                Envelope(
                    task_id=uuid4(),
                    target_gem="selenite",
                    payload=SeleniteRequest(
                        user_query=objective,
                        max_plan_depth=4 if self.training_wheels else 6,
                        context=ctx,
                    ),
                )
            )
            if res.error:
                return {"ok": False, "error": res.error.message[:200]}
            payload = res.payload
            plan = getattr(payload, "plan", None)
            return {
                "ok": True,
                "reasoning": getattr(plan, "reasoning", "") if plan else "",
                "n_steps": len(getattr(plan, "steps", []) or []) if plan else 0,
                "hypothesis": (getattr(plan, "reasoning", "") or "")[:300],
            }
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    def _labradorite(
        self,
        code: str,
        sandbox_result: Optional[Dict[str, Any]],
        original_failure: Optional[Dict[str, Any]],
        objective: str,
        task_id: str,
    ) -> Dict[str, Any]:
        """Always produce structured root_cause + smallest_experiment."""
        try:
            from core.schemas import Envelope, LabradoriteRequest
            res = self.registry.execute(
                Envelope(
                    task_id=uuid4(),
                    target_gem="labradorite",
                    payload=LabradoriteRequest(code=code or ""),
                )
            )
            critique_text = ""
            suggestions: List[str] = []
            complexity = 0.0
            confidence = 0.55
            if not res.error and res.payload:
                critique_text = getattr(res.payload, "critique", "") or ""
                suggestions = list(getattr(res.payload, "suggested_improvements", []) or [])
                complexity = float(getattr(res.payload, "complexity_score", 0) or 0)
                confidence = float(getattr(res.payload, "confidence_score", 0.55) or 0.55)

            root_cause = "unknown"
            evidence: List[str] = []
            if original_failure:
                reason = str(original_failure.get("reason") or original_failure.get("error") or "").lower()
                n_steps = original_failure.get("n_steps") or original_failure.get("max_steps")
                if "max_steps" in reason or (isinstance(n_steps, int) and n_steps >= 20):
                    root_cause = "budget_exhaust"
                    evidence.append(f"n_steps={n_steps}")
                elif "tool" in reason and ("order" in reason or "missing" in reason):
                    root_cause = "tool_order"
                elif "parse" in reason or "syntax" in reason:
                    root_cause = "parse_fail"
                elif "repair" in reason or "test" in reason:
                    root_cause = "repair_quality"
                elif sandbox_result and not sandbox_result.get("ok"):
                    root_cause = "sandbox_fail"
                    evidence.append(str(sandbox_result.get("stderr") or "")[:200])
                else:
                    root_cause = "verification_fail"

            smallest = {
                "hyp": "C" if root_cause == "tool_order" else "D" if root_cause == "repair_quality" else "B",
                "change": (
                    "force early high-value tool order (read → locate → edit)"
                    if root_cause == "tool_order"
                    else "one focused repair pass with asserts"
                    if root_cause == "repair_quality"
                    else "reduce scope or raise max_steps only after measured bottleneck"
                ),
                "mutation": (original_failure or {}).get("mutation") or objective[:80],
            }

            structured = {
                "timestamp": _now(),
                "task_id": task_id,
                "objective": objective[:500],
                "root_cause": root_cause,
                "evidence": evidence,
                "confidence": round(confidence, 3),
                "severity": "block" if root_cause in ("parse_fail",) else "improve",
                "critique": critique_text[:500],
                "suggested_improvements": suggestions[:10],
                "complexity_score": complexity,
                "smallest_experiment": smallest,
                "train_doctrine": "grok_v1",
                "training_wheels": self.training_wheels,
            }

            CRITIQUE_DIR.mkdir(parents=True, exist_ok=True)
            path = CRITIQUE_DIR / f"critique_{task_id[:12]}.json"
            _write_json(path, structured)
            structured["path"] = str(path.relative_to(ROOT))
            structured["ok"] = True
            return structured
        except Exception as e:
            return {"ok": False, "error": str(e)[:200], "root_cause": "critique_exception"}


def run_evolution_cycle(**kwargs) -> Dict[str, Any]:
    """Convenience entry point for host jobs and scripts."""
    return EvolutionController().run_cycle(**kwargs)


if __name__ == "__main__":
    # Host-agent entry: always structured JSON + clean exit under training wheels.
    try:
        result = run_evolution_cycle(
            objective="diagnose max_steps on hard ledger mutation",
            original_failure={"reason": "max_steps", "n_steps": 24, "mutation": "ledger_double"},
            code="# placeholder",
        )
        print(json.dumps(result, indent=2, default=str))
        sys.exit(0 if result.get("ok") else 1)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)[:400]}, indent=2))
        sys.exit(1)
