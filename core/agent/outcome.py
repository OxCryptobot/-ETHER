"""Outcome-based learning for the sota loop. The honest gate is the only reward.

- Reward comes from the goal's pytest run (tests_ok), nothing else. An infra
  outage, a goal that was already present, or an empty queue is not a model
  outcome and does not move the bandit.
- The bandit is the existing ``core.learning.BanditPolicy`` (same class, same
  arms, same reward scale via ``compute_reward``). Its state lives under the
  state root (``<root>/memory/learning/bandit.json``) so the Actions checkout
  does not wipe it every tick.
- Every attempt is stored as a short trajectory in
  ``<root>/memory/learning/trajectories.jsonl`` (capped).
- Behaviour only changes through a gate. With ``ETHER_SOTA_EXPLORE`` unset the
  loop uses the promoted arm for the bucket, else ``default`` (no prompt
  addon, byte-identical to the old prompt). An arm is promoted only after
  ``MIN_PASSES`` honest-gate passes and a bandit score above the incumbent.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

MIN_PASSES = 3
MARGIN = 0.05
DEMOTE_FAILS = 3
MAX_TRAJ = 2000
INCUMBENT = "default"


def _dir(root: Path) -> Path:
    return Path(root) / "memory" / "learning"


def bandit_path(root: Path) -> Path:
    return _dir(root) / "bandit.json"


def traj_path(root: Path) -> Path:
    return _dir(root) / "trajectories.jsonl"


def promoted_path(root: Path) -> Path:
    return _dir(root) / "promoted.json"


def explore_enabled() -> bool:
    return os.getenv("ETHER_SOTA_EXPLORE", "0") == "1"


def policy(root: Path):
    from core.learning import BanditPolicy

    return BanditPolicy(path=bandit_path(root))


@dataclass
class Pick:
    arm: str
    propensity: float
    reason: str
    context: Dict[str, Any]
    bucket: str
    addon: str = ""
    trace: Dict[str, Any] = field(default_factory=dict)


def context_for(root: Path) -> Dict[str, Any]:
    """phase from the last lesson; the sota ladder is single-file, tier 0."""
    try:
        from core.agent.sota import load

        lessons = [str(item) for item in (load(root).get("lessons") or [])]
    except Exception:
        lessons = []
    last = lessons[-1] if lessons else ""
    fail_kind = "tests_failed" if last.endswith("tests failed") else ""
    return {"tier": 0, "fail_kind": fail_kind, "multifile": False}


def propensity_of(pol, bucket: str, arm: str, reason: str) -> float:
    """Probability the epsilon-greedy select gave this arm. Logged for replay."""
    from core.learning import ArmStats

    arms = list(pol.arms)
    cs = pol.context_stats(bucket)
    untried = [a for a in arms if cs.arms.get(a, ArmStats()).pulls == 0]
    if reason == "cover":
        return 1.0 / max(1, len(untried))
    eps = pol.effective_epsilon(bucket)
    scores = {a: pol.score(bucket, a) for a in arms}
    best_score = max(scores.values())
    best = [a for a, s in scores.items() if s >= best_score - 1e-9]
    p = 0.0
    if arm in best:
        p += (1.0 - eps) / len(best)
    others_n = len(arms) - 1
    if others_n > 0:
        # an explore draw excludes the greedy arm actually drawn; average over it
        p += eps * sum(1.0 / len(best) for g in best if g != arm) / others_n
    return max(1e-6, min(1.0, p))


def promoted(root: Path) -> Dict[str, Any]:
    path = promoted_path(root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def choose(root: Path, explore: Optional[bool] = None) -> Pick:
    from core.learning import context_key, strategy_prompt_addon

    ctx = context_for(root)
    bucket = context_key(ctx)
    explore = explore_enabled() if explore is None else explore
    if explore:
        pol = policy(root)
        arm = pol.select(ctx)
        reason = str(pol.last_decision.get("reason") or "")
        prop = propensity_of(pol, bucket, arm, reason)
    else:
        row = promoted(root).get(bucket) or {}
        arm = str(row.get("arm") or INCUMBENT)
        reason, prop = ("promoted" if row else "incumbent"), 1.0
    addon = "" if arm == INCUMBENT else strategy_prompt_addon(arm)
    return Pick(arm=arm, propensity=prop, reason=reason, context=ctx, bucket=bucket, addon=addon)


def classify(result: Dict[str, Any]) -> str:
    if result.get("infra"):
        return "infra"
    note = str(result.get("note") or "")
    if note in ("found by search", "already present", "queue empty"):
        return "no_attempt"
    if result.get("ok") and result.get("tests_ok") is True:
        return "pass"
    return "fail"


def reward_for(kind: str) -> Optional[float]:
    from core.learning import compute_reward

    if kind == "pass":
        return compute_reward(
            exit_code=0, confidence=1.0, audit_approved=True, verification_score=1.0,
            plan_ok=True, first_compile_ok=True, holdout_ok=None,
        )
    if kind == "fail":
        return compute_reward(exit_code=1, confidence=0.0, audit_approved=False, plan_ok=True)
    return None


def _append(root: Path, row: Dict[str, Any]) -> None:
    """Append under the spine lock; trim to MAX_TRAJ with an atomic replace."""
    from core.spine.state_io import append_jsonl, state_lock

    path = traj_path(root)
    append_jsonl(path, row)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > MAX_TRAJ:
            tmp = path.with_name(path.name + ".trim")
            with state_lock(path.with_suffix(path.suffix + ".lock")):
                tmp.write_text("\n".join(lines[-MAX_TRAJ:]) + "\n", encoding="utf-8")
                os.replace(tmp, path)
    except Exception:
        pass


def trajectories(root: Path) -> List[Dict[str, Any]]:
    path = traj_path(root)
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def record(root: Path, pick: Pick, result: Dict[str, Any]) -> Dict[str, Any]:
    """Store the trajectory. Update the existing bandit only on a model outcome."""
    kind = classify(result)
    reward = reward_for(kind)
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "goal": result.get("goal"),
        "arm": pick.arm,
        "bucket": pick.bucket,
        "propensity": round(pick.propensity, 6),
        "reason": pick.reason,
        "kind": kind,
        "tests_ok": bool(result.get("tests_ok")),
        "reward": reward,
        "policy": "model",
        "spoiler": bool(pick.trace.get("spoiler")),
        "tools": pick.trace.get("tools") or [],
        "reply_tail": str(pick.trace.get("reply") or "")[-160:],
    }
    _append(root, row)
    if reward is not None:
        pol = policy(root)
        pol.update(pick.arm, reward, context=pick.context, extra=None)
        row["promote"] = maybe_promote(root, pick.bucket, pol)
    return row


def _arm_rows(rows: List[Dict[str, Any]], bucket: str, arm: str) -> List[Dict[str, Any]]:
    return [r for r in rows if r.get("bucket") == bucket and r.get("arm") == arm and r.get("kind") in ("pass", "fail")]


def maybe_promote(root: Path, bucket: str, pol=None) -> Dict[str, Any]:
    """Gated promote. Honest-gate passes only; demote after repeated fails."""
    pol = pol or policy(root)
    rows = trajectories(root)
    current = promoted(root)
    row = current.get(bucket) or {}
    incumbent = str(row.get("arm") or INCUMBENT)
    inc_rows = _arm_rows(rows, bucket, incumbent)
    if incumbent != INCUMBENT and len(inc_rows) >= DEMOTE_FAILS and all(
        r.get("kind") == "fail" for r in inc_rows[-DEMOTE_FAILS:]
    ):
        current.pop(bucket, None)
        _write_promoted(root, current)
        return {"action": "demote", "arm": incumbent}
    best: Optional[Dict[str, Any]] = None
    inc_score = pol.score(bucket, incumbent)
    for arm in pol.arms:
        if arm == incumbent:
            continue
        arm_rows = _arm_rows(rows, bucket, arm)
        passes = sum(1 for r in arm_rows if r.get("kind") == "pass" and r.get("tests_ok"))
        if passes < MIN_PASSES or not arm_rows or arm_rows[-1].get("kind") != "pass":
            continue
        score = pol.score(bucket, arm)
        if score <= inc_score + MARGIN:
            continue
        if best is None or score > best["score"]:
            best = {"arm": arm, "score": round(score, 4), "passes": passes}
    if best is None:
        return {"action": "hold", "arm": incumbent}
    current[bucket] = {**best, "from": incumbent, "ts": datetime.now(timezone.utc).isoformat()}
    _write_promoted(root, current)
    return {"action": "promote", **best}


def _write_promoted(root: Path, data: Dict[str, Any]) -> None:
    from core.spine.state_io import write_json

    write_json(promoted_path(root), data)


def summary(root: Path) -> Dict[str, Any]:
    rows = trajectories(root)
    graded = [r for r in rows if r.get("kind") in ("pass", "fail")]
    return {
        "trajectories": len(rows),
        "graded": len(graded),
        "passes": sum(1 for r in graded if r.get("kind") == "pass"),
        "spoiler_share": round(sum(1 for r in graded if r.get("spoiler")) / len(graded), 3) if graded else None,
        "promoted": promoted(root),
        "explore": explore_enabled(),
    }
