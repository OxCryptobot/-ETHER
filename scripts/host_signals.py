"""Batch 9: worst-signal health for the supervisor and host_main (audit W2, W33, W65).

Before: supervisor.json said 'running, failures 0' for days while `git pull` failed every cycle
(rc 128, local branch diverged), sota.json was stale, plan_error was set and the goal queue was
empty. `failures` counted only the writer pass's exit code.

health = the worst of all signals (ok < degraded < failing), each with a one-line reason:

  pull rc != 0                 degraded; failing after PULL_FAIL_FAILING consecutive cycles
  writer pass rc != 0          failing
  selfcheck_error              failing (a writer-path import is broken)
  plan_error / runtime_error / next_error / learning_error   degraded
  sota queue empty             degraded (nothing to learn from)
  artifacts/sota.json stale    degraded (no attempt for ETHER_HEALTH_SOTA_STALE_S)
  host_main.json stale         degraded

diverged(base) explains a failing pull: ahead/behind counts and the files the local-only commits
touch. It NEVER resets anything. The manual fix it writes to artifacts/pull_diverged.json is
`git reset --keep origin/main`, offered only when every local-only commit touches artifacts/ only.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

LEVELS = {"ok": 0, "degraded": 1, "failing": 2}
PULL_FAIL_FAILING = int(os.environ.get("ETHER_HEALTH_PULL_FAILING", "3"))
SOTA_STALE_S = float(os.environ.get("ETHER_HEALTH_SOTA_STALE_S", str(6 * 3600)))
HOST_STALE_S = float(os.environ.get("ETHER_HEALTH_HOST_STALE_S", str(2 * 3600)))
DIVERGED_NAME = "pull_diverged.json"
_TOKEN_RE = re.compile(r"(x-access-token:|ghp_|github_pat_|gho_)[^@\s'\"]*")


def redact(text: str) -> str:
    return _TOKEN_RE.sub(r"\1***", text or "")


def _sig(name: str, level: str, detail: str) -> Dict[str, str]:
    return {"name": name, "level": level, "detail": detail[:300]}


def _age_s(ts: Any, now: datetime) -> Optional[float]:
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).total_seconds()


def _read(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def host_signals(host: Dict[str, Any], *, base: Optional[Path] = None, now: Optional[datetime] = None,
                 check_age: bool = False) -> List[Dict[str, str]]:
    """Signals readable from one host_main.json row (plus sota.json when base is given)."""
    now = now or datetime.now(timezone.utc)
    out: List[Dict[str, str]] = []
    if not host:
        return [_sig("host_main", "degraded", "artifacts/host_main.json missing or unreadable")]
    if host.get("selfcheck_error"):
        out.append(_sig("selfcheck", "failing", str(host["selfcheck_error"])))
    for key in ("plan_error", "runtime_error", "next_error", "learning_error", "real_queue_error"):
        if host.get(key):
            out.append(_sig(key, "degraded", str(host[key])))
    jail = (host.get("selfcheck") or {}).get("gate_jail") if isinstance(host.get("selfcheck"), dict) else None
    if isinstance(jail, dict) and jail.get("mode") == "on" and jail.get("backend") in (None, "", "none"):
        out.append(_sig("gate_jail", "degraded", "ETHER_GATE_JAIL=1 but no jail backend passed the probe: every gate run is refused"))
    sota = host.get("sota") if isinstance(host.get("sota"), dict) else {}
    if sota.get("note") == "queue empty" or host.get("next_goal") == "none":
        out.append(_sig("queue", "degraded", "goal queue empty: nothing to learn from (planted goals: ETHER_PLANTED_GOALS)"))
    if check_age:
        age = _age_s(host.get("ts"), now)
        if age is None or age > HOST_STALE_S:
            out.append(_sig("host_main_stale", "degraded", f"host_main.json last written {int(age or -1)} s ago"))
    if base is not None:
        state = _read(Path(base) / "artifacts" / "sota.json")
        last = state.get("last") if isinstance(state.get("last"), dict) else {}
        age = _age_s(last.get("ts"), now) if last else None
        if state and (age is None or age > SOTA_STALE_S):
            out.append(_sig("sota_stale", "degraded",
                            f"no learning attempt recorded for {int(age) if age is not None else '?'} s (sota.json last.ts)"))
    return out


def pull_signals(pull: Dict[str, Any], streak: int) -> List[Dict[str, str]]:
    if not pull or pull.get("ok", True) or pull.get("note") == "no_git":
        return []
    level = "failing" if streak >= PULL_FAIL_FAILING else "degraded"
    why = pull.get("error") or f"rc {pull.get('rc')}"
    msg = f"git pull failed ({why}), {streak} cycle(s) in a row; the host is not receiving updates"
    div = pull.get("diverged") if isinstance(pull.get("diverged"), dict) else {}
    if div.get("fix"):
        msg += ". " + str(div["fix"])
    return [_sig("pull", level, msg)]


def pass_signals(res: Dict[str, Any]) -> List[Dict[str, str]]:
    if not res or res.get("ok", True):
        return []
    return [_sig("writer_pass", "failing", f"host_main pass rc {res.get('rc')}: {str(res.get('err_tail') or '')[-160:]}")]


def worst(signals: List[Dict[str, str]]) -> Dict[str, Any]:
    if not signals:
        return {"health": "ok", "worst": None, "signals": [], "n_bad": 0}
    top = max(signals, key=lambda s: LEVELS.get(s["level"], 0))
    return {"health": top["level"], "worst": f"{top['name']}: {top['detail']}", "signals": signals,
            "n_bad": len(signals)}


# ---------------------------------------------------------------- pull divergence

Runner = Callable[[List[str]], subprocess.CompletedProcess]


def _runner(base: Path) -> Runner:
    def run(argv: List[str]) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["GIT_TERMINAL_PROMPT"] = "0"
        return subprocess.run(["git", "-C", str(base), *argv], capture_output=True, text=True, timeout=60,
                              stdin=subprocess.DEVNULL, env=env)
    return run


def diverged(base: Path, run: Optional[Runner] = None, upstream: str = "origin/main") -> Dict[str, Any]:
    """Read-only: is the local branch ahead of / diverged from upstream, and what do the
    local-only commits touch? Never resets, rebases or fetches."""
    run = run or _runner(Path(base))
    try:
        p = run(["rev-list", "--left-right", "--count", f"HEAD...{upstream}"])
        if p.returncode != 0:
            return {"ok": False, "error": redact((p.stderr or "").strip())[-200:] or f"rc {p.returncode}"}
        ahead, behind = (int(x) for x in (p.stdout or "0 0").split()[:2])
        files: List[str] = []
        commits: List[str] = []
        if ahead:
            lg = run(["log", "--format=%h %s", f"{upstream}..HEAD"])
            commits = [c for c in (lg.stdout or "").splitlines() if c.strip()][:20]
            names = run(["log", "--name-only", "--format=", f"{upstream}..HEAD"])
            files = sorted({f.strip() for f in (names.stdout or "").splitlines() if f.strip()})
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:160]}"}
    artifacts_only = bool(files) and all(f.startswith("artifacts/") for f in files)
    row: Dict[str, Any] = {"ok": True, "ahead": ahead, "behind": behind, "diverged": ahead > 0 and behind > 0,
                           "local_only_commits": commits, "local_only_files": files[:50],
                           "artifacts_only": artifacts_only}
    if ahead and artifacts_only:
        row["fix"] = (f"Local branch is {ahead} commit(s) ahead / {behind} behind {upstream} and the local-only "
                      "commits touch only artifacts/. Manual fix on the host (not automatic): "
                      f"`git log {upstream}..HEAD --name-only` to confirm, then `git reset --keep {upstream}`.")
    elif ahead:
        row["fix"] = (f"Local branch is {ahead} commit(s) ahead / {behind} behind {upstream} and the local-only "
                      f"commits touch code ({', '.join(f for f in files if not f.startswith('artifacts/'))[:200]}). "
                      "Do NOT reset: inspect them (`git log -p " + upstream + "..HEAD`), push or re-apply the code "
                      "on origin, then reconcile by hand.")
    elif behind:
        row["fix"] = "Local branch is only behind; the pull failed for another reason (index lock, dirty files, network)."
    return row


def write_diverged(base: Path, info: Optional[Dict[str, Any]]) -> Optional[Path]:
    """artifacts/pull_diverged.json while the pull is failing; removed once it succeeds."""
    path = Path(base) / "artifacts" / DIVERGED_NAME
    if not info:
        try:
            path.unlink()
        except OSError:
            pass
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": datetime.now(timezone.utc).isoformat(), **info}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(row, indent=2, default=str) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path
