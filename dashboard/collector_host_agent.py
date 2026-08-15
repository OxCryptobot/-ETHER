"""Collect host_agent job queue, logs, foreman, apprentice lessons, RLHF, moonshots.

Path rule (non-negotiable): read what host_agent writes under artifacts/.
Never rely on memory/ for remote observability — it is gitignored.

2026-08-15 Control Matrix host-first:
- job class mix (fast/live/any)
- moonshot panels (smoothness, honest KPI, latency SLO, …)
- NO legacy flywheel/guardian/batch as primary health
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
PENDING = ROOT / "artifacts" / "jobs" / "pending"
DONE = ROOT / "artifacts" / "jobs" / "done"
FAILED = ROOT / "artifacts" / "jobs" / "failed"
LOG = ROOT / "artifacts" / "host_agent_log.txt"
STATUS = ROOT / "artifacts" / "host_agent_status.json"
LAST_JOB = ROOT / "artifacts" / "host_agent_last_job.json"
REPORT_MD = ROOT / "artifacts" / "host_report_latest.md"
REPORT_JSON = ROOT / "artifacts" / "host_report_latest.json"
FOREMAN_ARTIFACTS = ROOT / "artifacts" / "foreman_state.json"
FOREMAN_MEMORY = ROOT / "memory" / "host_agent" / "foreman_state.json"
LESSONS_ARTIFACTS = ROOT / "artifacts" / "lessons"
LESSONS_MEMORY = ROOT / "memory" / "ether_apprentice" / "lessons"
PREF_SUMMARY = ROOT / "artifacts" / "preference_summary.json"
STRATEGY_STATS = ROOT / "artifacts" / "strategy_stats.json"
WHATS_NEXT = ROOT / "artifacts" / "whats_next.json"
PERF_BENCH = ROOT / "artifacts" / "performance_benchmark.json"
ARTIFACTS = ROOT / "artifacts"


def _list_jobs(folder: Path, limit: int = 40) -> List[Dict[str, Any]]:
    if not folder.exists():
        return []
    out: List[Dict[str, Any]] = []
    for p in sorted(
        folder.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True
    ):
        if p.name == ".gitkeep":
            continue
        item: Dict[str, Any] = {
            "id": p.stem,
            "name": p.name,
            "mtime": datetime.fromtimestamp(
                p.stat().st_mtime, tz=timezone.utc
            ).isoformat(),
        }
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            item["sprint"] = data.get("sprint")
            item["note"] = data.get("note")
            item["created"] = data.get("created")
            item["source"] = data.get("source")
            item["class"] = data.get("class") or _infer_class(data)
            item["continue_on_fail"] = data.get("continue_on_fail")
        except Exception:
            pass
        out.append(item)
    return out[:limit]


def _infer_class(job: Dict[str, Any]) -> str:
    note = str(job.get("note") or "").lower()
    jid = str(job.get("id") or "").lower()
    hay = note + " " + jid
    if any(x in hay for x in ("live", "pipeline_ledger", "ss_pipeline_ledger")):
        return "live"
    if any(
        x in hay
        for x in (
            "scripted",
            "pytest",
            "ruff",
            "archive",
            "clean",
            "pref",
            "train_gates",
            "tool_runtime",
            "benchmark",
            "kill_live",
            "measure",
        )
    ):
        return "fast"
    return "any"


def _class_mix(jobs: List[Dict[str, Any]]) -> Dict[str, int]:
    mix = {"fast": 0, "live": 0, "any": 0}
    for j in jobs:
        cls = str(j.get("class") or "any").lower()
        if cls not in mix:
            cls = "any"
        mix[cls] += 1
    return mix


def _tail_log(max_lines: int = 120) -> List[str]:
    if not LOG.exists():
        return ["(no agent log yet — start scripts/host_agent.py)"]
    try:
        lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-max_lines:]
    except Exception as e:
        return [f"(log read error: {e})"]


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"error": str(e)}


def _read_text(path: Path, limit: int = 12000) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except Exception as e:
        return f"(read error: {e})"


def _lessons_summary() -> tuple[List[Dict[str, str]], str]:
    source = "none"
    folder = None
    if LESSONS_ARTIFACTS.exists() and any(LESSONS_ARTIFACTS.glob("*.json")):
        folder = LESSONS_ARTIFACTS
        source = "artifacts"
    elif LESSONS_MEMORY.exists():
        folder = LESSONS_MEMORY
        source = "memory_fallback"
    if folder is None:
        return [], source
    out: List[Dict[str, str]] = []
    for p in sorted(folder.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            out.append(
                {
                    "id": str(d.get("id") or p.stem),
                    "craft": str(d.get("craft") or ""),
                    "rule": str(d.get("rule") or "")[:200],
                }
            )
        except Exception:
            continue
    return out, source


def _foreman_state() -> tuple[Dict[str, Any], str]:
    if FOREMAN_ARTIFACTS.exists():
        return _read_json(FOREMAN_ARTIFACTS), "artifacts"
    if FOREMAN_MEMORY.exists():
        return _read_json(FOREMAN_MEMORY), "memory_fallback"
    return {}, "none"


def _exists(rel: str) -> bool:
    return (ROOT / rel).exists()


def _file_contains(rel: str, needle: str) -> bool:
    p = ROOT / rel
    if not p.exists():
        return False
    try:
        return needle in p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False


def _phase1_board() -> Dict[str, str]:
    board = {"1A": "unknown", "1B": "unknown", "1C": "unknown", "1D": "unknown"}

    has_method = _exists("core/coding_method.py")
    has_gate = _exists("core/loop/handlers/tool_runtime_gate.py")
    has_honest = _file_contains(
        "core/loop/handlers/tool_runtime_gate.py", "is_honest_tool_path_pass"
    )
    has_suffix = _file_contains("core/coding_method.py", "prompt_suffix")
    if has_method and has_gate and has_honest and has_suffix:
        board["1A"] = "LANDED"
    elif has_method or has_gate:
        board["1A"] = "PARTIAL"

    has_state = _exists("core/agent_state.py")
    used_in_evo = _file_contains("core/evolution_loop.py", "AgentState")
    if has_state and used_in_evo:
        board["1B"] = "LANDED"
    elif has_state:
        board["1B"] = "PARTIAL"

    prefer_patch = _file_contains("core/coding_method.py", "prefer_patch")
    apply_pref = _file_contains("core/coding_method.py", "apply_patch")
    doctrine = _exists("docs/APPRENTICE_CODING_DOCTRINE.md")
    if prefer_patch and apply_pref and doctrine:
        board["1C"] = "LANDED"
    elif prefer_patch or apply_pref:
        board["1C"] = "PARTIAL"

    rates = _read_json(ARTIFACTS / "honest_kpi.json")
    if rates.get("honest_tool_pass") and rates.get("tool_attempts"):
        board["1D"] = "LANDED" if (rates.get("honest_rate") or 0) > 0 else "BLOCKED"
    else:
        board["1D"] = "BLOCKED"

    return board


def _rlhf_block() -> Dict[str, Any]:
    pref = _read_json(PREF_SUMMARY)
    stats = _read_json(STRATEGY_STATS)
    ranked = pref.get("ranked_boosts") or []
    return {
        "n_preferences": pref.get("n_preferences"),
        "n_episodes": pref.get("n_episodes") or stats.get("n_episodes"),
        "updated": pref.get("updated") or stats.get("updated"),
        "rlhf": pref.get("rlhf"),
        "teacher": pref.get("teacher"),
        "ranked_boosts": ranked[:8],
        "strategies": pref.get("strategies") or stats.get("strategies") or {},
        "healthy": bool(pref.get("n_preferences")) and not pref.get("error"),
        "source": "artifacts/preference_summary.json",
    }


def _recent_scoreboards(limit: int = 8) -> List[Dict[str, Any]]:
    if not ARTIFACTS.exists():
        return []
    files = sorted(
        ARTIFACTS.glob("scoreboard*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    out: List[Dict[str, Any]] = []
    for p in files[:limit]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            summary = data.get("summary") or {}
            out.append(
                {
                    "id": p.stem,
                    "name": p.name,
                    "mtime": datetime.fromtimestamp(
                        p.stat().st_mtime, tz=timezone.utc
                    ).isoformat(),
                    "passed": summary.get("passed"),
                    "total": summary.get("total"),
                    "mode": summary.get("mode"),
                    "arms": summary.get("arms"),
                    "model": summary.get("model"),
                }
            )
        except Exception:
            out.append({"id": p.stem, "name": p.name, "error": "parse"})
    return out


def _critique_backlog(limit: int = 12) -> List[Dict[str, Any]]:
    paths: List[Path] = []
    if ARTIFACTS.exists():
        paths.extend(ARTIFACTS.glob("critique_*.json"))
        crit_dir = ARTIFACTS / "critiques"
        if crit_dir.exists():
            paths.extend(crit_dir.glob("critique_*.json"))
            paths.extend(crit_dir.glob("*.json"))
    paths = sorted(set(paths), key=lambda p: p.stat().st_mtime, reverse=True)
    out: List[Dict[str, Any]] = []
    for p in paths[:limit]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            out.append(
                {
                    "id": p.stem,
                    "name": p.name,
                    "mtime": datetime.fromtimestamp(
                        p.stat().st_mtime, tz=timezone.utc
                    ).isoformat(),
                    "root_cause": data.get("root_cause"),
                    "confidence": data.get("confidence"),
                    "smallest_experiment": str(
                        data.get("smallest_experiment") or ""
                    )[:180],
                    "job_id": data.get("job_id") or data.get("fail_job_id"),
                }
            )
        except Exception:
            out.append({"id": p.stem, "name": p.name, "error": "parse"})
    return out


def _throughput_signal(done: List[Dict[str, Any]], window_min: int = 30) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=window_min)
    count = 0
    for j in done:
        m = j.get("mtime")
        if not m:
            continue
        try:
            dt = datetime.fromisoformat(m.replace("Z", "+00:00"))
            if dt >= cutoff:
                count += 1
        except Exception:
            continue
    return {
        "window_min": window_min,
        "jobs_finished": count,
        "jobs_per_hour_est": round(count * (60 / max(1, window_min)), 1),
    }


def _fail_taxonomy(failed: List[Dict[str, Any]], last: Dict[str, Any]) -> Dict[str, Any]:
    types: Dict[str, int] = {}
    for j in failed[:20]:
        note = str(j.get("note") or "").lower()
        if "timeout" in note:
            types["timeout"] = types.get("timeout", 0) + 1
        elif "live" in note or "pipeline_ledger" in note:
            types["live_fail"] = types.get("live_fail", 0) + 1
        else:
            types["other"] = types.get("other", 0) + 1
    if last.get("failure_type"):
        ft = str(last["failure_type"])
        types[ft] = types.get(ft, 0) + 1
    return {"counts": types, "last_failure_type": last.get("failure_type")}


def _perf_summary(bench: Dict[str, Any]) -> Dict[str, Any]:
    if not bench or bench.get("error"):
        return {"available": False}
    scripted = (bench.get("scripted_baselines") or {}).get("pipeline_ledger") or {}
    direct = (bench.get("scripted_baselines") or {}).get("direct_hard_pack") or {}
    live = (bench.get("live_contrast") or {}).get("pipeline_ledger_live") or {}
    speed = bench.get("speedup") or {}
    ratio = (speed.get("scripted_vs_live_ledger") or {}).get("ratio")
    return {
        "available": True,
        "generated_at": bench.get("generated_at"),
        "scripted_ledger_s": scripted.get("elapsed_s"),
        "scripted_ledger_ok": scripted.get("ok"),
        "direct_hard_mean_s": direct.get("mean_elapsed_s"),
        "direct_hard_passed": f"{direct.get('passed')}/{direct.get('total')}",
        "live_ledger_s": live.get("elapsed_s"),
        "live_ledger_ok": live.get("ok"),
        "scripted_vs_live_ratio": ratio,
        "model": (bench.get("hardware") or {}).get("primary_model"),
        "targets": bench.get("targets"),
    }


def collect_host_agent() -> Dict[str, Any]:
    pending = _list_jobs(PENDING)
    done = _list_jobs(DONE, limit=60)
    failed = _list_jobs(FAILED)
    status = _read_json(STATUS)
    last = _read_json(LAST_JOB)
    report = _read_json(REPORT_JSON)
    report_md = _read_text(REPORT_MD)
    foreman, foreman_src = _foreman_state()
    lessons, lessons_src = _lessons_summary()
    rlhf = _rlhf_block()
    scoreboards = _recent_scoreboards()
    critiques = _critique_backlog()
    whats_next = _read_json(WHATS_NEXT)
    perf_bench = _read_json(PERF_BENCH)

    agent_alive = False
    if status.get("heartbeat"):
        try:
            hb = datetime.fromisoformat(
                status["heartbeat"].replace("Z", "+00:00")
            )
            age = (datetime.now(timezone.utc) - hb).total_seconds()
            agent_alive = age < 90
            status["heartbeat_age_s"] = round(age, 1)
        except Exception:
            pass

    pending_mix = _class_mix(pending)
    throughput = _throughput_signal(done)
    fail_tax = _fail_taxonomy(failed, last)
    perf = _perf_summary(perf_bench)

    moonshots: Dict[str, Any] = {}
    try:
        from dashboard.collector_moonshots import collect_moonshots

        moonshots = collect_moonshots()
    except Exception as e:
        moonshots = {"error": str(e)[:160], "tiles": []}

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "agent_alive": agent_alive,
        "truth": "host_agent",
        "status": status,
        "last_job": last,
        "whats_next": whats_next,
        "queue": {
            "pending": pending,
            "done": done,
            "failed": failed,
            "counts": {
                "pending": len(pending),
                "done": len(done),
                "failed": len(failed),
            },
            "class_mix_pending": pending_mix,
        },
        "control_matrix": {
            "live_skip_remaining": status.get("live_skip_remaining")
            or foreman.get("live_skip_remaining"),
            "foreman_mode": foreman.get("mode"),
            "foreman_cursor": foreman.get("cursor"),
            "class_mix_pending": pending_mix,
            "throughput": throughput,
            "fail_taxonomy": fail_tax,
            "last_ok": last.get("ok"),
            "last_failure_type": last.get("failure_type")
            or status.get("last_failure_type"),
            "performance": perf,
        },
        "moonshots": moonshots,
        "performance_benchmark": perf_bench
        if perf_bench and not perf_bench.get("error")
        else None,
        "log_lines": _tail_log(150),
        "report": report,
        "report_md": report_md,
        "foreman": foreman,
        "foreman_source": foreman_src,
        "apprentice": {
            "teacher": "grok",
            "lessons": lessons,
            "n": len(lessons),
            "source": lessons_src,
        },
        "phase1": _phase1_board(),
        "rlhf": rlhf,
        "scoreboards": scoreboards,
        "critiques": critiques,
        "paths": {
            "status": str(STATUS.relative_to(ROOT)),
            "log": str(LOG.relative_to(ROOT)),
            "last_job": str(LAST_JOB.relative_to(ROOT)),
            "whats_next": str(WHATS_NEXT.relative_to(ROOT)),
            "pref_summary": str(PREF_SUMMARY.relative_to(ROOT)),
            "performance_benchmark": "artifacts/performance_benchmark.json",
            "foreman_source": foreman_src,
            "lessons_source": lessons_src,
        },
    }
