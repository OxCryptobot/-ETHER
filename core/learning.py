"""@ETHER learning loop (honest ML-lite).

Not full RLHF / LoRA. What we implement for real, measurable improvement
on a GTX 1650-class machine:

1. Reward signal from sandbox + confidence + audit
2. Experience replay store (JSONL)
3. Epsilon-greedy contextual bandit over coding strategies

This is real online learning: arms get better estimates; policy shifts.
"""

from __future__ import annotations

import json
import math
import os
import random
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
LEARN_DIR = ROOT / "memory" / "learning"
EXPERIENCE_PATH = LEARN_DIR / "experience.jsonl"
BANDIT_PATH = LEARN_DIR / "bandit.json"

# Discrete strategies the bandit can select
STRATEGIES = [
    "default",
    "minimal",
    "with_asserts",
    "step_by_step",
    "no_context",
]


@dataclass
class ArmStats:
    pulls: int = 0
    total_reward: float = 0.0

    @property
    def mean(self) -> float:
        return self.total_reward / self.pulls if self.pulls else 0.0


def compute_reward(
    *,
    exit_code: Optional[int],
    confidence: float,
    audit_approved: bool,
    retries: int = 0,
) -> float:
    """Scalar reward in roughly [-1, 2]."""
    r = 0.0
    if exit_code == 0:
        r += 1.0
    elif exit_code is None:
        r -= 0.3
    else:
        r -= 0.7

    r += 0.5 * max(0.0, min(1.0, float(confidence or 0.0)))
    r += 0.3 if audit_approved else -0.2
    r -= 0.15 * max(0, int(retries))
    return round(r, 4)


class BanditPolicy:
    """Epsilon-greedy bandit over prompt/coding strategies."""

    def __init__(self, epsilon: float | None = None, path: Path = BANDIT_PATH):
        self.epsilon = (
            epsilon
            if epsilon is not None
            else float(os.getenv("ETHER_LEARN_EPSILON", "0.15"))
        )
        self.path = path
        self.arms: Dict[str, ArmStats] = {s: ArmStats() for s in STRATEGIES}
        self._load()

    def _load(self) -> None:
        LEARN_DIR.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for name, stats in (data.get("arms") or {}).items():
                self.arms[name] = ArmStats(
                    pulls=int(stats.get("pulls", 0)),
                    total_reward=float(stats.get("total_reward", 0.0)),
                )
        except Exception:
            pass

    def save(self) -> None:
        LEARN_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "epsilon": self.epsilon,
            "arms": {k: asdict(v) for k, v in self.arms.items()},
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def select(self) -> str:
        if random.random() < self.epsilon:
            return random.choice(STRATEGIES)
        # exploit: highest mean, tie-break by fewer pulls then random
        best_mean = max(a.mean for a in self.arms.values())
        candidates = [k for k, a in self.arms.items() if math.isclose(a.mean, best_mean) or a.mean == best_mean]
        return random.choice(candidates)

    def update(self, arm: str, reward: float) -> None:
        if arm not in self.arms:
            self.arms[arm] = ArmStats()
        self.arms[arm].pulls += 1
        self.arms[arm].total_reward += float(reward)
        self.save()

    def snapshot(self) -> Dict[str, Any]:
        return {
            "epsilon": self.epsilon,
            "arms": {
                k: {"pulls": v.pulls, "mean_reward": round(v.mean, 4), "total_reward": round(v.total_reward, 4)}
                for k, v in self.arms.items()
            },
            "best": max(self.arms.items(), key=lambda kv: kv[1].mean)[0] if self.arms else None,
        }


def append_experience(entry: Dict[str, Any]) -> None:
    LEARN_DIR.mkdir(parents=True, exist_ok=True)
    entry = {"timestamp": datetime.now(timezone.utc).isoformat(), **entry}
    with EXPERIENCE_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def strategy_prompt_addon(strategy: str) -> str:
    """Extra instructions injected into the coding prompt."""
    return {
        "default": "Write clean, correct Python only.",
        "minimal": "Write the shortest correct solution. No comments.",
        "with_asserts": "Include assert-based self-checks that print nothing extra on success.",
        "step_by_step": "Implement helper pieces clearly, then the final call/demo.",
        "no_context": "Ignore workspace context; solve from the objective alone.",
    }.get(strategy, "Write clean, correct Python only.")


def learning_enabled() -> bool:
    return os.getenv("ETHER_LEARNING", "1") == "1"
