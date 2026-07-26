"""Reward hygiene + expanded strategy arms + cold-arm decay."""

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
]
MIN_PULLS_BEFORE_GREEDY = 8
COLD_DECAY = 0.98  # per update on untouched arms when total pulls high


def learning_enabled() -> bool:
    return os.getenv("ETHER_LEARNING", "1") == "1"


def compute_reward(
    exit_code: Optional[int],
    confidence: float,
    audit_approved: bool,
    retries: int = 0,
    verification_score: float = 0.0,
    had_self_check: bool = False,
) -> float:
    """Strict reward: sandbox pass + audit + conf; soft penalty without self-check."""
    if exit_code is None:
        return -1.0
    if exit_code != 0:
        return round(-0.95 + 0.03 * min(retries, 2), 4)
    if not audit_approved:
        return -0.2
    conf = max(0.0, min(1.0, float(confidence)))
    ver = max(0.0, min(1.0, float(verification_score)))
    # gate-relevant blend
    r = 0.25 + 0.35 * conf + 0.25 * ver
    if had_self_check:
        r += 0.15
    else:
        r -= 0.1
    r -= 0.08 * min(retries, 3)
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

    def select(self) -> str:
        cold = [s for s, a in self.arms.items() if a.pulls < MIN_PULLS_BEFORE_GREEDY]
        if cold and random.random() < 0.45:
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
        # decay cold arms slightly so stale means don't dominate forever
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
    }.get(strategy, "Write clear executable code.")
