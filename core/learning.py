"""Reward + epsilon-greedy bandit (calibrated)."""

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

STRATEGIES = ["default", "minimal", "with_asserts", "step_by_step", "no_context"]
MIN_PULLS_BEFORE_GREEDY = 5


def learning_enabled() -> bool:
    return os.getenv("ETHER_LEARNING", "1") == "1"


def compute_reward(
    exit_code: Optional[int],
    confidence: float,
    audit_approved: bool,
    retries: int = 0,
) -> float:
    """Calibrated reward in roughly [-1, 1]."""
    if exit_code is None:
        return -1.0
    if exit_code != 0:
        return round(-0.9 + 0.05 * min(retries, 2), 4)
    r = 0.4
    r += 0.4 * max(0.0, min(1.0, confidence))
    r += 0.2 if audit_approved else -0.2
    r -= 0.1 * min(retries, 3)
    return round(max(-1.0, min(1.0, r)), 4)


@dataclass
class ArmStats:
    pulls: int = 0
    total_reward: float = 0.0

    @property
    def mean_reward(self) -> float:
        return self.total_reward / self.pulls if self.pulls else 0.0

    # alias used by some tests/callers
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
                    "total_reward": v.total_reward,
                    "mean_reward": v.mean_reward,
                }
                for k, v in self.arms.items()
            },
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def select(self) -> str:
        cold = [s for s, a in self.arms.items() if a.pulls < MIN_PULLS_BEFORE_GREEDY]
        if cold and random.random() < 0.5:
            return random.choice(cold)
        if random.random() < self.epsilon:
            return random.choice(list(self.arms.keys()))
        return max(self.arms.items(), key=lambda kv: kv[1].mean_reward)[0]

    def update(self, strategy: str, reward: float) -> None:
        if strategy not in self.arms:
            self.arms[strategy] = ArmStats()
        arm = self.arms[strategy]
        arm.pulls += 1
        arm.total_reward += reward
        self._save()
        append_experience({"strategy": strategy, "reward": reward})

    def snapshot(self) -> Dict:
        return {
            "epsilon": self.epsilon,
            "arms": {
                k: {
                    "pulls": v.pulls,
                    "total_reward": v.total_reward,
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
    }.get(strategy, "Write clear executable code.")
