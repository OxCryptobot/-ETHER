"""ETHER Evolution Loop — gems as agentic units (separate or one).

This is the executable infinity topology.

GEMS can be invoked independently (host jobs, CLI, tests) or as a single
coordinated unit via EvolutionController.run_cycle().

Hard rules:
- Labradorite is mandatory on every non-infra FAIL under training wheels.
- train_gates still gate every experience / preference write.
- One hypothesis per cycle when training_wheels=True.
- No LoRA weight updates here — only clean data + structured critique.
"""
from __future__ import annotations

import json
import os
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
    ) -> Dict[str, Any]:
        """One full evolution cycle.

        Returns a structured report that is also written to
        artifacts/evolution_<id>.json and (on FAIL) artifacts/critiques/.
        """
        tid = task_id or str(uuid4())
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
        }

        # --- 1. Selenite (plan / hypothesis) ---
        plan_out = self._selenite(objective, original_failure)
        report["stages"].append({"gem": "selenite", **plan_out})
        hypothesis = plan_out.get("hypothesis") or plan_out.get("reasoning") or ""

        # --- 2. Labradorite (mandatory on FAIL paths) ---
        must_critique = bool(original_failure) or not (sandbox_result or {}).get("ok", True)
        if must_critique or os.getenv("ETHER_FORCE_CRITIQUE", "0") == "1":
            crit = self._labradorite(code, sandbox_result, original_failure, objective, tid)
            report["stages"].append({"gem": "labradorite", **crit})
            report["root_cause"] = crit.get("root_cause")
            report["smallest_experiment"] = crit.get("smallest_experiment")
            report["critique_path"] = crit.get("path")
            # Feed memory bus so next Selenite sees it
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

        # --- 3. Citrine best-effort (already attempted inside record_critique) ---
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

            # Structured root-cause inference (deterministic, no extra LLM)
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
                elif "repair" in reason or "fix" in reason:
                    root_cause = "repair_quality"
                elif sandbox_result and not sandbox_result.get("ok"):
                    root_cause = "sandbox_fail"
                    evidence.append(str(sandbox_result.get("stderr") or "")[:200])
                else:
                    root_cause = "verification_fail"

            # Training-wheels: only one smallest experiment
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
    import pprint
    pprint.pprint(
        run_evolution_cycle(
            objective="diagnose max_steps on hard ledger mutation",
            original_failure={"reason": "max_steps", "n_steps": 24, "mutation": "ledger_double"},
            code="# placeholder",
        )
    )
