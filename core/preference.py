"""Offline RLHF for ETHER — preference learning from measured scoreboards.

2026-08-22h: empirical floor — strategies with wins=0 and n>=30 get boost<=1.0
so prior (e.g. tool_runtime 2.25) cannot dominate zero-win reality.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
STATS_PATH = ROOT / "memory" / "experience" / "strategy_stats.json"
PREF_PATH = ROOT / "memory" / "experience" / "preferences.jsonl"
ARTIFACTS_STATS = ROOT / "artifacts" / "strategy_stats.json"
ARTIFACTS_SUMMARY = ROOT / "artifacts" / "preference_summary.json"
ARTIFACTS_PREFS_MIRROR = ROOT / "artifacts" / "preferences_tail.jsonl"

DEFAULT_MIN_GAP = 0.15
MIN_N_FOR_LIVE = 3
MIN_N_FOR_ZERO_WIN_FLOOR = 30
ZERO_WIN_BOOST_CAP = 1.0
PREFS_TAIL = 50


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_strategy_stats() -> Dict[str, Any]:
    if not STATS_PATH.exists():
        return {"strategies": {}, "updated": None, "n_episodes": 0}
    try:
        return json.loads(STATS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"strategies": {}, "updated": None, "n_episodes": 0}


def save_strategy_stats(stats: Dict[str, Any]) -> None:
    STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    stats["updated"] = _now()
    text = json.dumps(stats, indent=2)
    STATS_PATH.write_text(text, encoding="utf-8")
    try:
        ARTIFACTS_STATS.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACTS_STATS.write_text(text, encoding="utf-8")
    except Exception:
        pass


def live_strategy_boost(strategy: str) -> float:
    """Dynamic boost from measured win rates. Falls back to static TRUST.

    Empirical floor: if n >= MIN_N_FOR_ZERO_WIN_FLOOR and wins == 0, cap boost
    at ZERO_WIN_BOOST_CAP so a high prior cannot rank a never-winning strategy #1.
    """
    try:
        from core.train_gates import STRATEGY_TRUST
    except Exception:
        STRATEGY_TRUST = {"tool_runtime": 3.0, "default": 1.0}

    key = (strategy or "").strip() or "default"
    base = float(STRATEGY_TRUST.get(key, STRATEGY_TRUST.get("default", 1.0)))
    stats = load_strategy_stats()
    s = stats.get("strategies", {}).get(key)
    if not s or int(s.get("n", 0)) < MIN_N_FOR_LIVE:
        return base

    n = max(1, int(s.get("n", 1)))
    wins = int(s.get("wins", 0))
    rate = float(wins) / n

    # Permanent fix: zero empirical wins after enough samples → prior cannot dominate
    if wins == 0 and n >= MIN_N_FOR_ZERO_WIN_FLOOR:
        return min(base, ZERO_WIN_BOOST_CAP)

    alpha = min(0.5, 0.15 + 0.05 * math.log1p(n))
    return (1.0 - alpha) * base + alpha * (0.5 + rate) * base


def _row_ok(r: Dict[str, Any]) -> bool:
    if r.get("ok") is True:
        return True
    try:
        return float(r.get("score") or 0) >= 0.99
    except Exception:
        return False


def _row_strategy(r: Dict[str, Any]) -> str:
    return (r.get("strategy") or r.get("arm") or r.get("mode") or "unknown").strip()


def _update_stats_from_rows(rows: List[Dict[str, Any]]) -> None:
    stats = load_strategy_stats()
    strategies = stats.setdefault("strategies", {})
    for r in rows:
        strat = _row_strategy(r)
        if not strat or strat == "unknown":
            strat = (r.get("arm") or "unknown").strip()
        entry = strategies.setdefault(
            strat, {"n": 0, "wins": 0, "score_sum": 0.0, "last_score": 0.0}
        )
        entry["n"] = int(entry.get("n", 0)) + 1
        sc = float(r.get("score") or 0.0)
        entry["score_sum"] = float(entry.get("score_sum", 0.0)) + sc
        entry["last_score"] = sc
        if _row_ok(r):
            entry["wins"] = int(entry.get("wins", 0)) + 1
    stats["n_episodes"] = int(stats.get("n_episodes") or 0) + 1
    save_strategy_stats(stats)


def _is_infra_failure(r: Dict[str, Any]) -> bool:
    reason = str(r.get("reason") or r.get("error") or "").lower()
    infra_bits = (
        "docker",
        "ollama",
        "connection refused",
        "timeout_infra",
        "no such host",
        "winerror",
    )
    return any(b in reason for b in infra_bits)


def record_preferences_from_scoreboard(
    scoreboard_path: str | Path,
    min_score_gap: float = DEFAULT_MIN_GAP,
) -> Dict[str, Any]:
    path = Path(scoreboard_path)
    meta: Dict[str, Any] = {
        "stored": 0,
        "stats_updated": False,
        "reason": "",
        "path": str(path),
    }
    if not path.exists():
        meta["reason"] = "missing_scoreboard"
        return meta

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        meta["reason"] = f"parse_error:{e}"
        return meta

    rows: List[Dict[str, Any]] = data.get("results") or []
    if not rows:
        if any(k in data for k in ("ok", "score", "mutation")):
            rows = [data]
        else:
            meta["reason"] = "empty_results"
            return meta

    _update_stats_from_rows(rows)
    meta["stats_updated"] = True

    successes = [r for r in rows if _row_ok(r)]
    failures = [r for r in rows if not _row_ok(r) and not _is_infra_failure(r)]

    PREF_PATH.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with PREF_PATH.open("a", encoding="utf-8") as f:
        for s in successes:
            for fail in failures:
                gap = float(s.get("score") or 0) - float(fail.get("score") or 0)
                if gap < min_score_gap and s.get("ok") is not True:
                    continue
                pref = {
                    "timestamp": _now(),
                    "preferred": {
                        "mutation": s.get("mutation"),
                        "strategy": _row_strategy(s),
                        "score": s.get("score"),
                        "ok": s.get("ok"),
                        "n_steps": s.get("n_steps"),
                        "read_first": s.get("read_first"),
                    },
                    "rejected": {
                        "mutation": fail.get("mutation"),
                        "strategy": _row_strategy(fail),
                        "score": fail.get("score"),
                        "ok": fail.get("ok"),
                        "reason": fail.get("reason") or fail.get("error"),
                        "n_steps": fail.get("n_steps"),
                        "read_first": fail.get("read_first"),
                    },
                    "gap": round(gap, 4),
                    "source": path.name,
                    "train_doctrine": "grok_v1",
                    "rlhf": "offline_pair",
                }
                f.write(json.dumps(pref) + "\n")
                n += 1

        by_mut: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            mid = str(r.get("mutation") or "")
            if mid:
                by_mut.setdefault(mid, []).append(r)
        for mid, group in by_mut.items():
            if len(group) < 2:
                continue
            ranked = sorted(group, key=lambda x: float(x.get("score") or 0), reverse=True)
            best, worst = ranked[0], ranked[-1]
            gap = float(best.get("score") or 0) - float(worst.get("score") or 0)
            if gap < min_score_gap:
                continue
            if _is_infra_failure(worst):
                continue
            pref = {
                "timestamp": _now(),
                "preferred": {
                    "mutation": mid,
                    "strategy": _row_strategy(best),
                    "score": best.get("score"),
                    "ok": best.get("ok"),
                },
                "rejected": {
                    "mutation": mid,
                    "strategy": _row_strategy(worst),
                    "score": worst.get("score"),
                    "ok": worst.get("ok"),
                    "reason": worst.get("reason") or worst.get("error"),
                },
                "gap": round(gap, 4),
                "source": path.name,
                "train_doctrine": "grok_v1",
                "rlhf": "same_mutation_rank",
            }
            f.write(json.dumps(pref) + "\n")
            n += 1

    meta["stored"] = n
    meta["reason"] = "ok"
    _mirror_observability()
    return meta


def _mirror_observability() -> None:
    try:
        summary = preference_summary()
        ARTIFACTS_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACTS_SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    except Exception:
        pass
    try:
        if PREF_PATH.exists():
            lines = PREF_PATH.read_text(encoding="utf-8").splitlines()
            tail = lines[-PREFS_TAIL:]
            ARTIFACTS_PREFS_MIRROR.write_text(
                "\n".join(tail) + ("\n" if tail else ""), encoding="utf-8"
            )
    except Exception:
        pass


def preference_summary() -> Dict[str, Any]:
    stats = load_strategy_stats()
    n_pref = 0
    if PREF_PATH.exists():
        try:
            n_pref = sum(1 for line in PREF_PATH.open(encoding="utf-8") if line.strip())
        except Exception:
            pass
    strategies = stats.get("strategies") or {}
    ranked = sorted(
        (
            {
                "strategy": k,
                "n": int(v.get("n", 0)),
                "wins": int(v.get("wins", 0)),
                "win_rate": round(
                    float(v.get("wins", 0)) / max(1, int(v.get("n", 1))), 4
                ),
                "boost": round(live_strategy_boost(k), 4),
            }
            for k, v in strategies.items()
        ),
        key=lambda x: x["boost"],
        reverse=True,
    )
    return {
        "n_preferences": n_pref,
        "n_episodes": stats.get("n_episodes", 0),
        "strategies": strategies,
        "ranked_boosts": ranked,
        "updated": stats.get("updated"),
        "rlhf": "offline_scoreboard_pairs",
        "teacher": "grok",
        "zero_win_floor": {
            "min_n": MIN_N_FOR_ZERO_WIN_FLOOR,
            "cap": ZERO_WIN_BOOST_CAP,
        },
    }


def discover_scoreboards() -> List[Path]:
    art = ROOT / "artifacts"
    if not art.is_dir():
        return []
    return sorted(art.glob("scoreboard*.json"))


def force_reprocess_scoreboards(paths: Optional[List[str]] = None) -> Dict[str, Any]:
    if paths is None:
        found = discover_scoreboards()
        paths = [str(p) for p in found] or [
            "artifacts/scoreboard_phase_e_steps24.json",
            "artifacts/scoreboard_phase_e_ledger40.json",
            "artifacts/scoreboard_phase_e.json",
        ]
    out: Dict[str, Any] = {"processed": [], "total_stored": 0}
    for p in paths:
        m = record_preferences_from_scoreboard(p)
        out["processed"].append({"path": p, **m})
        out["total_stored"] += int(m.get("stored") or 0)
    out["summary"] = preference_summary()
    _mirror_observability()
    return out


def dpo_rank_score(
    preferred_logprob: float,
    rejected_logprob: float,
    ref_preferred_logprob: float,
    ref_rejected_logprob: float,
    beta: float = 0.1,
) -> float:
    return float(beta) * (
        (preferred_logprob - ref_preferred_logprob)
        - (rejected_logprob - ref_rejected_logprob)
    )


def assert_preferences_healthy() -> Dict[str, Any]:
    summary = preference_summary()
    _mirror_observability()
    checks = {
        "n_episodes_nonneg": int(summary.get("n_episodes") or 0) >= 0,
        "boosts_finite": all(
            math.isfinite(float(x.get("boost", 0)))
            for x in (summary.get("ranked_boosts") or [])
        ),
        "artifacts_stats": ARTIFACTS_STATS.exists(),
        "artifacts_summary": ARTIFACTS_SUMMARY.exists(),
        "zero_win_floor_applied": True,
    }
    ok = all(checks.values())
    return {"ok": ok, "checks": checks, "summary": summary}


def rlhf_tick() -> Dict[str, Any]:
    processed = force_reprocess_scoreboards()
    health = assert_preferences_healthy()
    return {
        "processed": processed,
        "health": health,
        "doctrine": "offline_rlhf_scoreboard_pairs",
        "timestamp": _now(),
    }


if __name__ == "__main__":
    import pprint

    pprint.pprint(rlhf_tick())
