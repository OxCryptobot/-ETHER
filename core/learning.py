"""Reward hygiene + process rewards + contextual bandit (auto tier)."""

from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
BANDIT_PATH = ROOT / "memory" / "learning" / "bandit.json"
EXP_PATH = ROOT / "memory" / "learning" / "experience.jsonl"


@dataclass(frozen=True)
class ArmBehaviour:
    """What an arm actually *does* differently."""

    prompt_addon: str
    use_workspace_context: bool = True
    use_experience: bool = True
    use_few_shot: bool = True
    force_repo_map: bool = False


STRATEGY_BEHAVIOUR: Dict[str, ArmBehaviour] = {
    "default": ArmBehaviour(
        prompt_addon="Write clear, complete executable code.",
    ),
    "minimal": ArmBehaviour(
        prompt_addon="Minimal code only. No comments. Shortest correct solution.",
    ),
    "with_asserts": ArmBehaviour(
        prompt_addon="Include assert self-checks for the main behavior.",
    ),
    "repair_heavy": ArmBehaviour(
        prompt_addon="Be defensive; validate inputs; avoid edge-case crashes.",
    ),
    "no_context": ArmBehaviour(
        prompt_addon="Solve from the objective alone; no repository context is provided.",
        use_workspace_context=False,
        use_experience=False,
        use_few_shot=False,
    ),
    "repo_map_on": ArmBehaviour(
        prompt_addon="Prefer names/symbols consistent with the repository map.",
        force_repo_map=True,
    ),
    # Stage 3: real multi-file generation using # file: markers.
    "multifile": ArmBehaviour(
        prompt_addon=(
            "When multiple modules are needed, emit them as:\n"
            "# file: util.py\n<code>\n# file: main.py\n<code>\n"
            "Entry module runs asserts. Prefer pure functions. No markdown."
        ),
        force_repo_map=True,
    ),
}

STRATEGIES: List[str] = list(STRATEGY_BEHAVIOUR)

RETIRED_STRATEGIES: Tuple[str, ...] = (
    "step_by_step",
    "few_shot_on",
    "rag_on",
    "burst_on_fail",
)

PHASE_GEN = "gen"
PHASE_REPAIR_SYNTAX = "repair_syntax"
PHASE_REPAIR_LOGIC = "repair_logic"

_SYNTAX_KINDS = {
    "SyntaxError",
    "syntax",
    "IndentationError",
    "NameError",
    "ImportError",
    "ModuleNotFoundError",
}

CONTEXT_HINTS: Dict[str, Tuple[str, ...]] = {
    PHASE_REPAIR_SYNTAX: ("repair_heavy", "minimal"),
    PHASE_REPAIR_LOGIC: ("with_asserts", "repair_heavy"),
}
SCOPE_HINTS: Dict[str, Tuple[str, ...]] = {
    "complex": ("multifile", "repo_map_on"),
}

PRIOR_WEIGHT = 2.0
HINT_BONUS = 0.15
EPSILON_FLOOR = 0.02
EPSILON_ANNEAL_PULLS = 25.0


def learning_enabled() -> bool:
    return os.getenv("ETHER_LEARNING", "1") == "1"


def compute_reward(
    exit_code: Optional[int],
    confidence: float,
    audit_approved: bool,
    retries: int = 0,
    verification_score: float = 0.0,
    had_self_check: bool = False,
    plan_ok: bool = True,
    first_compile_ok: bool = False,
    used_burst: bool = False,
    holdout_ok: Optional[bool] = None,
) -> float:
    if exit_code is None:
        return -1.0
    if holdout_ok is False:
        return -0.9
    if exit_code != 0:
        base = -0.95 + 0.05 * min(retries, 2)
        if plan_ok:
            base += 0.05
        return round(max(-1.0, min(0.0, base)), 4)
    if not audit_approved:
        return -0.2
    conf = max(0.0, min(1.0, float(confidence)))
    ver = max(0.0, min(1.0, float(verification_score)))
    r = 0.15 + 0.30 * conf + 0.25 * ver
    if plan_ok:
        r += 0.08
    if first_compile_ok:
        r += 0.12
    else:
        r -= 0.05 * min(retries, 3)
    if had_self_check:
        r += 0.12
    else:
        r -= 0.08
    if used_burst:
        r -= 0.05
    if holdout_ok:
        r += 0.25
    elif holdout_ok is None:
        r = min(r, 0.75)
    return round(max(-1.0, min(1.0, r)), 4)


def phase_for(fail_kind: str) -> str:
    fk = (fail_kind or "").strip()
    if not fk:
        return PHASE_GEN
    if fk in _SYNTAX_KINDS:
        return PHASE_REPAIR_SYNTAX
    return PHASE_REPAIR_LOGIC


def context_key(context: Optional[Dict[str, Any]]) -> str:
    ctx = context or {}
    phase = phase_for(str(ctx.get("fail_kind") or ""))
    try:
        tier = int(ctx.get("tier") or 0)
    except (TypeError, ValueError):
        tier = 0
    complex_task = bool(ctx.get("multifile")) or tier >= 2
    return f"{phase}|{'complex' if complex_task else 'simple'}"


def hinted_arms(bucket: str) -> Tuple[str, ...]:
    phase, _, scope = bucket.partition("|")
    hints = list(CONTEXT_HINTS.get(phase, ()))
    hints += [a for a in SCOPE_HINTS.get(scope, ()) if a not in hints]
    return tuple(a for a in hints if a in STRATEGY_BEHAVIOUR)


@dataclass
class ArmStats:
    pulls: int = 0
    total_reward: float = 0.0

    @property
    def mean_reward(self) -> float:
        return self.total_reward / self.pulls if self.pulls else 0.0

    @property
    def mean(self) -> float:
        return self.mean_reward

    def as_dict(self) -> Dict[str, float]:
        return {
            "pulls": self.pulls,
            "total_reward": round(self.total_reward, 6),
            "mean_reward": round(self.mean_reward, 4),
        }


@dataclass
class ContextStats:
    arms: Dict[str, ArmStats] = field(default_factory=dict)

    def arm(self, name: str) -> ArmStats:
        return self.arms.setdefault(name, ArmStats())

    @property
    def pulls(self) -> int:
        return sum(a.pulls for a in self.arms.values())

    @property
    def mean_reward(self) -> float:
        pulls = self.pulls
        if not pulls:
            return 0.0
        return sum(a.total_reward for a in self.arms.values()) / pulls


class BanditPolicy:
    def __init__(self, epsilon: Optional[float] = None, path: Optional[Path] = None):
        self.epsilon = float(
            epsilon if epsilon is not None else os.getenv("ETHER_LEARN_EPSILON", "0.15")
        )
        self.path = Path(path) if path is not None else BANDIT_PATH
        self.arms: Dict[str, ArmStats] = {s: ArmStats() for s in STRATEGIES}
        self.contexts: Dict[str, ContextStats] = {}
        self.retired: Dict[str, ArmStats] = {}
        self.last_decision: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return
        try:
            for k, v in (data.get("arms") or {}).items():
                stats = ArmStats(
                    pulls=int(v.get("pulls", 0)),
                    total_reward=float(v.get("total_reward", 0.0)),
                )
                if k in STRATEGY_BEHAVIOUR:
                    self.arms[k] = stats
                else:
                    self.retired[k] = stats
            for k, v in (data.get("retired_arms") or {}).items():
                self.retired.setdefault(
                    k,
                    ArmStats(
                        pulls=int(v.get("pulls", 0)),
                        total_reward=float(v.get("total_reward", 0.0)),
                    ),
                )
            for bucket, arms in (data.get("contexts") or {}).items():
                cs = self.contexts.setdefault(str(bucket), ContextStats())
                for name, v in (arms or {}).items():
                    if name not in STRATEGY_BEHAVIOUR:
                        continue
                    cs.arms[name] = ArmStats(
                        pulls=int(v.get("pulls", 0)),
                        total_reward=float(v.get("total_reward", 0.0)),
                    )
            for s in STRATEGIES:
                self.arms.setdefault(s, ArmStats())
            if "epsilon" in data:
                self.epsilon = float(data["epsilon"])
        except Exception:
            pass

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "epsilon": self.epsilon,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "arms": {k: v.as_dict() for k, v in self.arms.items()},
            "contexts": {
                bucket: {name: a.as_dict() for name, a in cs.arms.items()}
                for bucket, cs in sorted(self.contexts.items())
            },
            "retired_arms": {k: v.as_dict() for k, v in sorted(self.retired.items())},
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def context_stats(self, bucket: str) -> ContextStats:
        return self.contexts.setdefault(bucket, ContextStats())

    def score(self, bucket: str, arm: str) -> float:
        cs = self.context_stats(bucket)
        stats = cs.arms.get(arm, ArmStats())
        prior = cs.mean_reward + (HINT_BONUS if arm in hinted_arms(bucket) else 0.0)
        return (stats.total_reward + PRIOR_WEIGHT * prior) / (stats.pulls + PRIOR_WEIGHT)

    def effective_epsilon(self, bucket: str) -> float:
        pulls = self.context_stats(bucket).pulls
        eps = self.epsilon / (1.0 + pulls / EPSILON_ANNEAL_PULLS)
        return max(EPSILON_FLOOR, min(self.epsilon, eps))

    def select(self, context: Optional[Dict] = None) -> str:
        ctx = dict(context or {})
        if "tier" not in ctx:
            try:
                from core.curriculum import current_tier_index

                ctx["tier"] = current_tier_index()
            except Exception:
                ctx["tier"] = 0

        bucket = context_key(ctx)
        cs = self.context_stats(bucket)
        arms = list(self.arms)

        untried = [a for a in arms if cs.arms.get(a, ArmStats()).pulls == 0]
        if untried:
            choice, reason = random.choice(untried), "cover"
        else:
            scores = {a: self.score(bucket, a) for a in arms}
            best_score = max(scores.values())
            best = [a for a, s in scores.items() if s >= best_score - 1e-9]
            greedy = random.choice(best)
            eps = self.effective_epsilon(bucket)
            others = [a for a in arms if a != greedy]
            if others and random.random() < eps:
                choice, reason = random.choice(others), "explore"
            else:
                choice, reason = greedy, "exploit"

        self.last_decision = {
            "arm": choice,
            "bucket": bucket,
            "reason": reason,
            "epsilon": round(self.effective_epsilon(bucket), 4),
        }
        return choice

    def update(
        self,
        strategy: str,
        reward: float,
        context: Optional[Dict] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        reward = float(reward)
        if strategy not in self.arms:
            self.arms[strategy] = ArmStats()
        arm = self.arms[strategy]
        arm.pulls += 1
        arm.total_reward += reward

        bucket = context_key(context) if context is not None else ""
        if bucket:
            ctx_arm = self.context_stats(bucket).arm(strategy)
            ctx_arm.pulls += 1
            ctx_arm.total_reward += reward

        self._save()
        row: Dict[str, Any] = {"strategy": strategy, "reward": reward, "context": bucket}
        if extra:
            row.update(extra)
        append_experience(row)

    def snapshot(self) -> Dict:
        return {
            "epsilon": self.epsilon,
            "arms": {k: v.as_dict() for k, v in self.arms.items()},
            "contexts": {
                bucket: {name: a.as_dict() for name, a in cs.arms.items()}
                for bucket, cs in sorted(self.contexts.items())
            },
            "retired_arms": {k: v.as_dict() for k, v in sorted(self.retired.items())},
        }


def append_experience(row: Dict) -> None:
    EXP_PATH.parent.mkdir(parents=True, exist_ok=True)
    row = {"timestamp": datetime.now(timezone.utc).isoformat(), **row}
    with EXP_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


_FALLBACK_BEHAVIOUR = ArmBehaviour(prompt_addon="Write clear executable code.")


def arm_behaviour(strategy: str) -> ArmBehaviour:
    return STRATEGY_BEHAVIOUR.get(strategy, _FALLBACK_BEHAVIOUR)


def strategy_prompt_addon(strategy: str) -> str:
    return arm_behaviour(strategy).prompt_addon
