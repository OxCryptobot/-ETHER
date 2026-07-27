"""Reward hygiene + process rewards + contextual bandit (auto tier)."""

from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
BANDIT_PATH = ROOT / "memory" / "learning" / "bandit.json"
EXP_PATH = ROOT / "memory" / "learning" / "experience.jsonl"

STRATEGIES = [
    "default",
    "minimal",
    "with_asserts",
    "step_by_step",
    "no_context",
    "few_shot_on",
    "repo_map_on",
    "repair_heavy",
    "rag_on",
    "burst_on_fail",
]
MIN_PULLS_BEFORE_GREEDY = 8
COLD_DECAY = 0.98


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
    """Reward for a completed run.

    `holdout_ok` is the verdict from assertions the generator never saw
    (core/holdout.py). None means the task supplied no holdout.

    Every other input here is self-graded: confidence, verification_score and
    had_self_check all derive from assertions the model wrote about its own
    output. Optimising on those alone makes "write assertions that cannot
    fail" the highest-scoring strategy, which is exactly what the arm table
    had started to learn. When a holdout exists it therefore dominates.
    """
    if exit_code is None:
        return -1.0
    if holdout_ok is False:
        # Failed assertions it was not shown. Self-graded confidence is
        # irrelevant — this is a wrong answer that merely ran.
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
        # Passing unseen assertions is the only evidence here that the model
        # could not have manufactured, so it outweighs the self-graded terms.
        r += 0.25
    elif holdout_ok is None:
        # Ungraded. Cap below a holdout-verified run so the bandit can never
        # prefer a task/strategy that avoids independent grading.
        r = min(r, 0.75)
    return round(max(-1.0, min(1.0, r)), 4)


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


class BanditPolicy:
    def __init__(self, epsilon: Optional[float] = None, path: Optional[Path] = None):
        self.epsilon = float(
            epsilon if epsilon is not None else os.getenv("ETHER_LEARN_EPSILON", "0.15")
        )
        self.path = Path(path) if path is not None else BANDIT_PATH
        self.arms: Dict[str, ArmStats] = {s: ArmStats() for s in STRATEGIES}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for k, v in (data.get("arms") or {}).items():
                self.arms[k] = ArmStats(
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
            "arms": {
                k: {
                    "pulls": v.pulls,
                    "total_reward": round(v.total_reward, 6),
                    "mean_reward": round(v.mean_reward, 4),
                }
                for k, v in self.arms.items()
            },
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def select(self, context: Optional[Dict] = None) -> str:
        ctx = dict(context or {})
        if "tier" not in ctx:
            try:
                from core.curriculum import current_tier_index

                ctx["tier"] = current_tier_index()
            except Exception:
                ctx["tier"] = 0

        preferred = []
        tier = int(ctx.get("tier") or 0)
        fail_kind = str(ctx.get("fail_kind") or "")
        multifile = bool(ctx.get("multifile"))
        if fail_kind in ("SyntaxError", "syntax", "NameError", "ImportError"):
            preferred.extend(["repair_heavy", "with_asserts", "minimal"])
        if multifile or tier >= 2:
            preferred.extend(["repo_map_on", "few_shot_on", "rag_on"])
        if tier >= 3:
            preferred.append("burst_on_fail")
        preferred = [p for p in preferred if p in self.arms]

        cold = [s for s, a in self.arms.items() if a.pulls < MIN_PULLS_BEFORE_GREEDY]
        if cold and random.random() < 0.35:
            return random.choice(cold)
        if preferred and random.random() < 0.40:
            return random.choice(preferred)
        if random.random() < self.epsilon:
            return random.choice(list(self.arms.keys()))
        return max(self.arms.items(), key=lambda kv: kv[1].mean_reward)[0]

    def update(self, strategy: str, reward: float) -> None:
        if strategy not in self.arms:
            self.arms[strategy] = ArmStats()
        arm = self.arms[strategy]
        arm.pulls += 1
        arm.total_reward += reward
        total_pulls = sum(a.pulls for a in self.arms.values())
        if total_pulls > 30:
            for name, a in self.arms.items():
                if name != strategy and a.pulls > 0 and a.pulls < MIN_PULLS_BEFORE_GREEDY:
                    a.total_reward *= COLD_DECAY
        self._save()
        append_experience({"strategy": strategy, "reward": reward})

    def snapshot(self) -> Dict:
        return {
            "epsilon": self.epsilon,
            "arms": {
                k: {
                    "pulls": v.pulls,
                    "total_reward": round(v.total_reward, 4),
                    "mean_reward": round(v.mean_reward, 4),
                }
                for k, v in self.arms.items()
            },
        }


def append_experience(row: Dict) -> None:
    EXP_PATH.parent.mkdir(parents=True, exist_ok=True)
    row = {"timestamp": datetime.now(timezone.utc).isoformat(), **row}
    with EXP_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def strategy_prompt_addon(strategy: str) -> str:
    return {
        "default": "Write clear, complete executable code.",
        "minimal": "Minimal code only. No comments. Shortest correct solution.",
        "with_asserts": "Include assert self-checks for the main behavior.",
        "step_by_step": "Use small helper steps; keep main logic obvious.",
        "no_context": "Ignore workspace context; solve from the objective alone.",
        "few_shot_on": "Follow prior success patterns closely; mirror structure of examples.",
        "repo_map_on": "Prefer names/symbols consistent with the repository map.",
        "repair_heavy": "Be defensive; validate inputs; avoid edge-case crashes.",
        "rag_on": "Reuse patterns from retrieved repository snippets when relevant.",
        "burst_on_fail": "Prefer a robust, well-tested solution; include asserts.",
    }.get(strategy, "Write clear executable code.")
