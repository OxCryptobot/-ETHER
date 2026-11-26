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
DEFAULT_PROMOTE_RULE = "posterior"


def _dir(root: Path) -> Path:
    return Path(root) / "memory" / "learning"


def bandit_path(root: Path, kind: str = "") -> Path:
    """One bandit per goal kind: the legacy ladder keeps bandit.json."""
    return _dir(root) / (f"bandit_{kind}.json" if kind else "bandit.json")


def traj_path(root: Path) -> Path:
    return _dir(root) / "trajectories.jsonl"


def promoted_path(root: Path) -> Path:
    return _dir(root) / "promoted.json"


def explore_enabled(goal: Optional[Dict[str, Any]] = None) -> bool:
    """Legacy ladder: off unless ETHER_SOTA_EXPLORE=1. Real goals (fix_test/lint/refactor):
    on unless ETHER_SOTA_EXPLORE=0. Exploring only changes the prompt/context strategy;
    the honest gate and the regression guard decide every keep, and promotion stays gated."""
    flag = os.getenv("ETHER_SOTA_EXPLORE")
    if (goal or {}).get("kind") in ("fix_test", "lint", "refactor"):
        return flag != "0"
    return flag == "1"


def policy(root: Path, kind: str = ""):
    from core.learning import BanditPolicy

    return BanditPolicy(path=bandit_path(root, kind))


def real_kind(goal: Optional[Dict[str, Any]]) -> str:
    kind = str((goal or {}).get("kind") or "")
    return kind if kind in ("fix_test", "lint", "refactor") else ""


def promo_key(kind: str, bucket: str) -> str:
    return f"{kind}:{bucket}" if kind else bucket


@dataclass
class Pick:
    arm: str
    propensity: float
    reason: str
    context: Dict[str, Any]
    bucket: str
    addon: str = ""
    trace: Dict[str, Any] = field(default_factory=dict)
    kind: str = ""


def context_for(root: Path, goal: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """phase from the last lesson; tier 0 = legacy ladder, 1 = lint, 2 = failing test,
    3 = refactor. Real goal kinds get their own bandit bucket so a promotion learned on
    one kind never changes another."""
    tier = {"lint": 1, "fix_test": 2, "refactor": 3}.get(str((goal or {}).get("kind") or ""), 0)
    if tier:
        hard = str((goal or {}).get("error_kind") or "") == "AssertionError"
        return {"tier": tier, "fail_kind": "tests_failed" if hard else "", "multifile": False}
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


def choose(root: Path, explore: Optional[bool] = None, goal: Optional[Dict[str, Any]] = None) -> Pick:
    from core.learning import context_key

    ctx = context_for(root, goal)
    bucket = context_key(ctx)
    kind = real_kind(goal)
    if explore is None:
        explore = explore_enabled(goal)
    drawn = None
    if explore:
        from core.agent import evolve_es

        if evolve_es.enabled():
            drawn = evolve_es.sample(root, bucket)
    if drawn is not None:
        arm, prop = drawn
        reason = "es"
    elif explore and kind and _bandit_algo(kind) != "egreedy":
        from core.agent import bandit

        arm, prop, reason, btrace = bandit.choose(root, kind, bucket, goal=goal, tries=_tries(root, goal))
        pick = Pick(arm=arm, propensity=prop, reason=reason, context=ctx, bucket=bucket,
                    addon="" if arm == INCUMBENT else _addon(arm), kind=kind)
        pick.trace["bandit"] = btrace
        pick.trace["goal"] = {k: (goal or {}).get(k) for k in ("via", "error_kind", "kind", "tractability")}
        return pick
    elif explore:
        pol = policy(root, kind)
        arm = pol.select(ctx)
        reason = str(pol.last_decision.get("reason") or "")
        prop = propensity_of(pol, bucket, arm, reason)
    else:
        row = promoted(root).get(promo_key(kind, bucket)) or {}
        arm = str(row.get("arm") or INCUMBENT)
        reason, prop = ("promoted" if row else "incumbent"), 1.0
    addon = "" if arm == INCUMBENT else _addon(arm)
    return Pick(arm=arm, propensity=prop, reason=reason, context=ctx, bucket=bucket, addon=addon, kind=kind)


def _bandit_algo(kind: str) -> str:
    from core.agent import bandit

    return bandit.algo(kind)


def _addon(arm: str) -> str:
    from core.agent import bandit
    from core.learning import strategy_prompt_addon

    fb = bandit.factored_behaviour(arm)
    return fb.prompt_addon if fb is not None else strategy_prompt_addon(arm)


def _tries(root: Path, goal: Optional[Dict[str, Any]]) -> int:
    if not goal or not goal.get("id"):
        return 0
    try:
        from core.agent import goal_source

        return int((goal_source.load_index(root).get("tries") or {}).get(goal["id"], 0))
    except Exception:
        return 0


def reward01(kind: str, result: Dict[str, Any]) -> Optional[int]:
    """Honest-gate reward on a 0/1 scale: 1 = target passed with 0 regressions (gate kept the
    edit), 0 = the model produced something the gate refused. None = not a model outcome."""
    if kind == "pass":
        return 1 if result.get("tests_ok") is True and not int(result.get("regressions") or 0) else 0
    if kind == "fail":
        return 0
    return None


def classify(result: Dict[str, Any]) -> str:
    if result.get("infra"):
        return "infra"
    if result.get("gate_abort"):
        # batch 10 item 0: the baseline never ran, no model call was made. 18 of the last 25
        # recorded attempts on the host were these, graded as model failures (reward -0.9).
        return "no_attempt"
    note = str(result.get("note") or "")
    if note in ("found by search", "already present", "queue empty") or note.startswith("rejected"):
        return "no_attempt"
    if result.get("policy") == "tool":
        return "tool"  # rule-based edit (refactor): no model call, credits its own strategy table
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
        "bucket": promo_key(pick.kind, pick.bucket),
        "propensity": round(pick.propensity, 6),
        "reason": pick.reason,
        "kind": kind,
        "tests_ok": bool(result.get("tests_ok")),
        "reward": reward,
        "policy": "tool" if kind == "tool" else "model",
        "secs": round(float(pick.trace.get("secs") or 0.0), 1),
        "algo": (pick.trace.get("bandit") or {}).get("algo") or ("egreedy" if pick.reason in
                                                                ("cover", "explore", "exploit") else pick.reason),
        "spoiler": bool(pick.trace.get("spoiler")),
        "goal_kind": result.get("kind") or "legacy",
        "regressions": result.get("regressions"),
        "prompt_chars": pick.trace.get("prompt_chars"),
        "tools": pick.trace.get("tools") or [],
        "reply_tail": str(pick.trace.get("reply") or "")[-160:],
        "note": str(result.get("note") or "")[:60],
        "via": (pick.trace.get("goal") or {}).get("via"),
        "reply_cap": pick.trace.get("reply_cap"),
    }
    if pick.trace.get("exemplar"):
        row["exemplar"] = pick.trace.get("exemplar")  # batch 7: which kept edit was shown
    if pick.trace.get("reply_hash"):  # batch 8: duplicate-reply measurement (decisions unchanged)
        from core.agent.sampling import seen_before

        prior = trajectories(root)
        row["reply_hash"] = pick.trace["reply_hash"]
        row["file_hash"] = pick.trace.get("file_hash")
        row["dup"] = seen_before(prior, str(result.get("goal") or ""), pick.trace["reply_hash"])
    if "temp" in pick.trace:
        row["temp"] = pick.trace.get("temp")
    if result.get("planted") or row.get("via") == "planted":
        row["planted"] = True  # batch 10 item 5d: planted keeps are curriculum, not product progress
    if isinstance(pick.trace.get("swarm_shadow"), dict):  # batch 10 item 5c: ETHER_SWARM=record
        row["shadow_would_reject"] = bool(pick.trace["swarm_shadow"].get("would_reject"))
        row["shadow_why"] = str(pick.trace["swarm_shadow"].get("why") or "")[:60]
    if isinstance(pick.trace.get("swarm"), dict):  # batch 10 item 5: ETHER_SWARM=1 model calls / survivors
        row["swarm_k"] = int(pick.trace["swarm"].get("k") or 0)
        row["swarm_valid"] = int(pick.trace["swarm"].get("valid") or 0)
    if pick.trace.get("dedup_skipped"):
        row["dedup_skipped_from_cache"] = True
    if "exemplar_eligible" in (pick.trace.get("bandit") or {}):
        row["exemplar_eligible"] = bool(pick.trace["bandit"]["exemplar_eligible"])
    r01 = reward01(kind, result) if pick.kind in ("fix_test", "lint") else None
    if r01 is not None:
        row["reward01"] = r01
    _append(root, row)
    if r01 is not None:
        try:
            from core.agent import bandit

            row["bandit4"] = bandit.record(root, pick.kind, pick.bucket, pick.arm, r01,
                                           secs=float(pick.trace.get("secs") or 0.0), goal=pick.trace.get("goal"))
        except Exception as exc:
            row["bandit4_error"] = type(exc).__name__
    if reward is not None and not pick.arm.startswith("f:"):
        pol = policy(root, pick.kind)
        pol.update(pick.arm, reward, context=pick.context, extra=None)
        row["promote"] = maybe_promote(root, pick.bucket, pol, kind=pick.kind)
        if (row["promote"] or {}).get("action") in ("promote", "demote"):
            _log_promotion(root, pick, row["promote"])
        try:
            from core.agent import evolve_es

            graded = [r for r in trajectories(root) if r.get("kind") in ("pass", "fail")]
            if evolve_es.enabled() and graded and len(graded) % 10 == 0:
                row["es"] = {k: v for k, v in evolve_es.propose(root).items() if k != "policy"}
        except Exception as exc:
            row["es_error"] = type(exc).__name__
    return row


def promotions_path(root: Path) -> Path:
    return _dir(root) / "promotions.jsonl"


def _log_promotion(root: Path, pick: Pick, verdict: Dict[str, Any]) -> None:
    """Promotion / demotion events, capped like trajectories (published as counts)."""
    from core.spine.state_io import append_jsonl

    path = promotions_path(root)
    append_jsonl(path, {"ts": datetime.now(timezone.utc).isoformat(), "key": promo_key(pick.kind, pick.bucket),
                        "action": verdict.get("action"), "arm": verdict.get("arm"), "from": verdict.get("from")})
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > 200:
            tmp = path.with_name(path.name + ".trim")
            tmp.write_text("\n".join(lines[-200:]) + "\n", encoding="utf-8")
            os.replace(tmp, path)
    except Exception:
        pass


def promotions(root: Path) -> List[Dict[str, Any]]:
    path = promotions_path(root)
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _arm_rows(rows: List[Dict[str, Any]], bucket: str, arm: str) -> List[Dict[str, Any]]:
    return [r for r in rows if r.get("bucket") == bucket and r.get("arm") == arm and r.get("kind") in ("pass", "fail")]


def maybe_promote(root: Path, bucket: str, pol=None, kind: str = "") -> Dict[str, Any]:
    """Gated promote. Honest-gate passes only; demote after repeated fails."""
    pol = pol or policy(root, kind)
    rows = trajectories(root)
    current = promoted(root)
    key = promo_key(kind, bucket)
    row = current.get(key) or {}
    incumbent = str(row.get("arm") or INCUMBENT)
    inc_rows = _arm_rows(rows, key, incumbent)
    if incumbent != INCUMBENT and len(inc_rows) >= DEMOTE_FAILS and all(
        r.get("kind") == "fail" for r in inc_rows[-DEMOTE_FAILS:]
    ):
        current.pop(key, None)
        _write_promoted(root, current)
        return {"action": "demote", "arm": incumbent}
    best: Optional[Dict[str, Any]] = None
    inc_score = pol.score(bucket, incumbent)
    posterior = promote_rule(kind) == "posterior"
    if posterior:
        from core.agent import bandit

        stats4 = (bandit.load(root, kind).get("buckets") or {}).get(bucket) or {}
    for arm in pol.arms:
        if arm == incumbent:
            continue
        arm_rows = _arm_rows(rows, key, arm)
        passes = sum(1 for r in arm_rows if r.get("kind") == "pass" and r.get("tests_ok"))
        if passes < MIN_PASSES or not arm_rows or arm_rows[-1].get("kind") != "pass":
            continue
        if posterior:
            score = bandit.prob_better(stats4, arm, incumbent, seed=len(rows))
            if score < bandit.PROMOTE_PROB:
                continue
        else:
            score = pol.score(bucket, arm)
            if score <= inc_score + MARGIN:
                continue
        if best is None or score > best["score"]:
            best = {"arm": arm, "score": round(score, 4), "passes": passes}
    if best is None:
        return {"action": "hold", "arm": incumbent}
    current[key] = {**best, "from": incumbent, "ts": datetime.now(timezone.utc).isoformat()}
    _write_promoted(root, current)
    return {"action": "promote", **best}


def promote_rule(kind: str = "") -> str:
    """Batch 4: "posterior" = >= MIN_PASSES and P(arm beats incumbent) >= 0.9 under the 0/1 Beta
    posteriors (real kinds only); "score" = batch-2 rule (score > incumbent + MARGIN)."""
    if kind not in ("fix_test", "lint"):
        return "score"
    rule = os.getenv("ETHER_PROMOTE_RULE", DEFAULT_PROMOTE_RULE).strip().lower()
    return rule if rule in ("score", "posterior") else DEFAULT_PROMOTE_RULE


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
        "explore_legacy": explore_enabled(),
        "explore_real": explore_enabled({"kind": "fix_test"}),
        "by_kind": {k: sum(1 for r in graded if (r.get("goal_kind") or "legacy") == k and r.get("kind") == "pass")
                    for k in sorted({(r.get("goal_kind") or "legacy") for r in graded})},
    }


# ---------------------------------------------------------------- published summary (batch 3)

SUMMARY_PATH = "artifacts/learning_summary.json"
SUMMARY_MAX_BYTES = 16384
SUMMARY_RECENT = 25
_SAFE_ID = __import__("re").compile(r"[^A-Za-z0-9_.:\-/\[\]]+")
_SAFE_FIELDS = ("ts", "goal", "arm", "goal_kind", "kind", "reward", "regressions", "prompt_chars", "spoiler",
                "tests_ok", "reward01", "secs", "algo", "note", "via", "exemplar", "temp", "dup")


def _safe(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return round(value, 4) if isinstance(value, float) else value
    return _SAFE_ID.sub("_", str(value))[:80]


REVERT_NOTES = ("regression", "tests failed", "siblings failed")


def _entropy(counts: Dict[str, int]) -> float:
    import math

    tot = sum(counts.values())
    return round(-sum((n / tot) * math.log2(n / tot) for n in counts.values() if n), 4) if tot else 0.0


def metrics(root: Path, rows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Batch-4 improvement metrics, all from honest-gate trajectories (docs/BANDITS.md).

    kept = a model edit the gate kept (tests_ok, 0 regressions). A session is one UTC day
    of host ticks. GPU-hours are the wall seconds of graded model attempts (guard runs
    included, so this undercounts kept/GPU-hour slightly)."""
    from core.agent.goal_quality import filler_id

    rows = trajectories(root) if rows is None else rows
    graded = [r for r in rows if r.get("kind") in ("pass", "fail") and (r.get("goal_kind") or "legacy") != "legacy"]
    kept = [r for r in graded if r.get("kind") == "pass" and r.get("tests_ok") and not int(r.get("regressions") or 0)]
    secs = sum(float(r.get("secs") or 0.0) for r in graded)
    days: Dict[str, Dict[str, int]] = {}
    for r in graded:
        d = str(r.get("ts") or "")[:10] or "?"
        cell = days.setdefault(d, {"attempts": 0, "kept": 0})
        cell["attempts"] += 1
        cell["kept"] += 1 if r in kept else 0
    reverted = [r for r in graded if r.get("kind") == "fail" and str(r.get("note") or "") in REVERT_NOTES]
    by_kind: Dict[str, Dict[str, int]] = {}
    for r in graded:
        k = _safe(r.get("goal_kind"))
        by_kind.setdefault(k, {})
        a = _safe(r.get("arm") or "?")
        by_kind[k][a] = by_kind[k].get(a, 0) + 1
    by_via: Dict[str, Dict[str, int]] = {}
    for r in graded:
        cell = by_via.setdefault(_safe(r.get("via") or r.get("goal_kind")), {"attempts": 0, "kept": 0})
        cell["attempts"] += 1
        cell["kept"] += 1 if r in kept else 0
    events = promotions(root)
    all_kept = [r for r in rows if r.get("kind") == "pass"]
    return {
        "attempts": len(graded),
        "kept": len(kept),
        "kept_per_attempt": round(len(kept) / len(graded), 4) if graded else None,
        "gpu_hours": round(secs / 3600.0, 3),
        "kept_per_gpu_hour": round(len(kept) / (secs / 3600.0), 3) if secs > 0 else None,
        "sessions": {d: days[d] for d in sorted(days)[-7:]},
        "kept_per_session": round(len(kept) / len(days), 3) if days else None,
        "filler_rate": round(sum(1 for r in all_kept if filler_id(str(r.get("goal") or ""))) / len(all_kept), 4)
        if all_kept else 0.0,
        "revert_rate": round(len(reverted) / len(graded), 4) if graded else None,
        "regressions_caught": sum(1 for r in rows if int(r.get("regressions") or 0) > 0),
        "promotions": sum(1 for e in events if e.get("action") == "promote"),
        "demotions": sum(1 for e in events if e.get("action") == "demote"),
        "arm_entropy_bits": {k: _entropy(v) for k, v in sorted(by_kind.items())},
        "tool_edits": sum(1 for r in rows if r.get("kind") == "tool"),
        "by_via": by_via,  # decides when per-via (contextual) arms are worth turning on
        # batch 8: share of graded attempts whose edit repeated one already tried on the same goal,
        # and kept/attempts by sampling temperature (decides ETHER_SAMPLE_TEMP / ETHER_DEDUP_REPLY)
        "dup_share": (round(sum(1 for r in graded if r.get("dup")) / len([r for r in graded if "dup" in r]), 4)
                      if any("dup" in r for r in graded) else None),
        "by_temp": _by_temp(graded, kept),
        **_swarm_metrics(graded, kept),
        **_real_vs_planted(graded, kept, filler_id),
    }


def _is_planted(r: Dict[str, Any]) -> bool:
    return bool(r.get("planted")) or r.get("via") == "planted"


def _real_vs_planted(graded: List[Dict[str, Any]], kept: List[Dict[str, Any]], filler_id: Any) -> Dict[str, Any]:
    """Batch 10 item 5d: real_kept (failing-test / lint goals of this repo), planted_kept (validated
    planted bugs in scratch copies) and filler_rate_real = filler share of real keeps only (the live
    filler_rate 0.9556 is legacy-ladder keeps, which say nothing about real goals)."""
    real = [r for r in kept if not _is_planted(r)]
    real_graded = [r for r in graded if not _is_planted(r)]
    return {
        "real_attempts": len(real_graded),
        "real_kept": len(real),
        "planted_attempts": len(graded) - len(real_graded),
        "planted_kept": len(kept) - len(real),
        "filler_rate_real": round(sum(1 for r in real if filler_id(str(r.get("goal") or ""))) / len(real), 4)
        if real else 0.0,
    }


def _swarm_metrics(graded: List[Dict[str, Any]], kept: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Batch 10 item 5c: ETHER_SWARM=record shadow verdicts (would_reject_kept > 0 = a critic would have
    thrown away a keep: kill signal) and ETHER_SWARM=1 model calls / survivors."""
    out: Dict[str, Any] = {}
    sh = [r for r in graded if "shadow_would_reject" in r]
    if sh:
        out["swarm_shadow"] = {"n": len(sh), "would_reject": sum(1 for r in sh if r["shadow_would_reject"]),
                               "would_reject_kept": sum(1 for r in sh if r["shadow_would_reject"] and r in kept)}
    sw = [r for r in graded if "swarm_k" in r]
    if sw:
        out["swarm"] = {"attempts": len(sw), "model_calls": sum(int(r.get("swarm_k") or 0) for r in sw),
                        "valid": sum(int(r.get("swarm_valid") or 0) for r in sw)}
    return out


def _by_temp(graded: List[Dict[str, Any]], kept: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    out: Dict[str, Dict[str, int]] = {}
    for r in graded:
        if "temp" not in r:
            continue
        cell = out.setdefault(str(r.get("temp")), {"attempts": 0, "kept": 0})
        cell["attempts"] += 1
        cell["kept"] += 1 if r in kept else 0
    return out


def summary_doc(root: Path) -> Dict[str, Any]:
    """Learning, visible from GitHub. Whitelisted fields only: no prompts, replies, paths
    outside the repo, env, or tokens. memory/ stays private; this is a derived view."""
    rows = trajectories(root)
    graded = [r for r in rows if r.get("kind") in ("pass", "fail")]
    arms: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for r in graded:
        kind = _safe(r.get("goal_kind") or "legacy")
        cell = arms.setdefault(kind, {}).setdefault(_safe(r.get("arm") or "?"),
                                                    {"pulls": 0, "passes": 0, "reward_sum": 0.0, "regressions": 0})
        cell["pulls"] += 1
        cell["passes"] += 1 if r.get("kind") == "pass" else 0
        cell["reward_sum"] += float(r.get("reward") or 0.0)
        cell["regressions"] += int(r.get("regressions") or 0)
    for kind in arms.values():
        for cell in kind.values():
            cell["pass_rate"] = round(cell["passes"] / cell["pulls"], 3) if cell["pulls"] else None
            cell["mean_reward"] = round(cell.pop("reward_sum") / cell["pulls"], 3) if cell["pulls"] else None
    real = [r for r in graded if (r.get("goal_kind") or "legacy") != "legacy"]
    doc: Dict[str, Any] = {
        "schema": 2,
        "generated": datetime.now(timezone.utc).isoformat(),
        "totals": {
            "trajectories": len(rows),
            "graded": len(graded),
            "passes": sum(1 for r in graded if r.get("kind") == "pass"),
            "real_graded": len(real),
            "real_passes": sum(1 for r in real if r.get("kind") == "pass"),
            "regressions_reverted": sum(1 for r in rows if int(r.get("regressions") or 0) > 0),
            "spoiler_share": round(sum(1 for r in graded if r.get("spoiler")) / len(graded), 3) if graded else None,
        },
        "explore": {"legacy": explore_enabled(), "real": explore_enabled({"kind": "fix_test"})},
        "promoted": {_safe(k): _safe(v.get("arm") if isinstance(v, dict) else v)
                     for k, v in list((promoted(root) or {}).items())[:20]},
        "arms": arms,
        "recent": [{f: _safe(r.get(f)) for f in _SAFE_FIELDS if f in r} for r in rows[-SUMMARY_RECENT:]],
    }
    try:
        doc["metrics"] = metrics(root, rows)
    except Exception as exc:
        doc["metrics"] = {"error": type(exc).__name__}
    try:
        from core.agent import bandit

        doc["bandit"] = bandit.summary(root)
    except Exception as exc:
        doc["bandit"] = {"error": type(exc).__name__}
    try:
        from core.agent import exemplars

        if exemplars.mode() != "0":  # batch 7: library size + reuse (counts only, no diffs published)
            doc["exemplars"] = {k: _safe(v) for k, v in exemplars.summary(root, rows).items()}
    except Exception as exc:
        doc["exemplars"] = {"error": type(exc).__name__}
    try:
        from core.agent import goal_source

        data = goal_source.load_index(root)
        reasons: Dict[str, int] = {}
        for why in (data.get("dropped") or {}).values():
            reasons[_safe(why)] = reasons.get(_safe(why), 0) + 1
        doc["real_queue"] = {"open": len(goal_source.ranked(root)), "done": len(data.get("done") or []),
                             "dropped": reasons}
        why = goal_source.why_blocked(root)  # batch 10 item 0: open != selectable; say why
        doc["real_queue"].update({"selectable": why.get("selectable"), "blocked": why.get("blocked"),
                                  "next_retry": why.get("next_retry")})
    except Exception:
        pass
    return doc


def publish_summary(root: Path) -> Dict[str, Any]:
    """Write artifacts/learning_summary.json (atomic, <= SUMMARY_MAX_BYTES)."""
    doc = summary_doc(root)
    text = json.dumps(doc, indent=1, sort_keys=True)
    while len(text.encode("utf-8")) > SUMMARY_MAX_BYTES and doc["recent"]:
        doc["recent"] = doc["recent"][len(doc["recent"]) // 2 + 1:] if len(doc["recent"]) > 1 else []
        text = json.dumps(doc, indent=1, sort_keys=True)
    if len(text.encode("utf-8")) > SUMMARY_MAX_BYTES:
        doc["arms"] = {"truncated": True}
        text = json.dumps(doc, indent=1, sort_keys=True)
    if len(text.encode("utf-8")) > SUMMARY_MAX_BYTES:
        doc["bandit"] = {"truncated": True, "algo": (doc.get("bandit") or {}).get("algo")}
        (doc.get("metrics") or {}).pop("sessions", None)
        text = json.dumps(doc, indent=1, sort_keys=True)
    path = Path(root) / SUMMARY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return {"ok": True, "bytes": len(text) + 1, "graded": doc["totals"]["graded"]}
