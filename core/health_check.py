"""Automated system health checks — operational + intelligence gates."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "memory" / "health"
LATEST = OUT_DIR / "latest.json"
HISTORY = OUT_DIR / "history.jsonl"


@dataclass
class Check:
    id: str
    ok: bool
    severity: str  # critical | high | medium | low | info
    message: str
    detail: str = ""
    duration_ms: float = 0.0
    tip: str = ""


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


def _tcp(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def _http_ok(url: str, timeout: float = 2.0) -> bool:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= getattr(resp, "status", 200) < 500
    except Exception:
        return False


def check_python() -> Check:
    t0 = time.perf_counter()
    ver = sys.version.split()[0]
    ok = sys.version_info >= (3, 10)
    return Check(
        id="python",
        ok=ok,
        severity="critical" if not ok else "info",
        message=f"Python {ver}",
        detail=sys.executable,
        duration_ms=_ms(t0),
        tip="Need Python 3.10+ in project venv",
    )


def check_git() -> Check:
    t0 = time.perf_counter()
    if not shutil.which("git"):
        return Check("git", False, "high", "git not on PATH", duration_ms=_ms(t0))
    merge = (ROOT / ".git" / "MERGE_HEAD").exists()
    if merge:
        return Check(
            "git",
            False,
            "critical",
            "MERGE_HEAD present — unfinished merge",
            tip="git merge --abort then git fetch && git reset --hard origin/main",
            duration_ms=_ms(t0),
        )
    try:
        p = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=8,
        )
        sha = (p.stdout or "").strip() or "?"
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=8,
        )
        dirty_n = len([ln for ln in (dirty.stdout or "").splitlines() if ln.strip()])
        return Check(
            "git",
            True,
            "info" if dirty_n == 0 else "low",
            f"HEAD {sha}" + (f" · {dirty_n} dirty paths" if dirty_n else " · clean"),
            duration_ms=_ms(t0),
        )
    except Exception as e:
        return Check("git", False, "high", f"git error: {e}", duration_ms=_ms(t0))


def check_ollama() -> Check:
    t0 = time.perf_counter()
    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    model = os.getenv("ETHER_PRIMARY_MODEL", "")
    bin_ok = shutil.which("ollama") is not None
    up = _http_ok(base + "/api/tags") or _tcp("127.0.0.1", 11434)
    if not up:
        return Check(
            "ollama",
            False,
            "critical",
            "Ollama not reachable",
            detail=base,
            tip="Start ollama serve; set OLLAMA_BASE_URL",
            duration_ms=_ms(t0),
        )
    msg = f"up · model={model or '(unset)'}"
    sev = "info" if model else "medium"
    if not model:
        msg += " — set ETHER_PRIMARY_MODEL from `ollama list`"
    return Check(
        "ollama",
        True,
        sev,
        msg,
        detail=f"binary={'yes' if bin_ok else 'no'} {base}",
        duration_ms=_ms(t0),
        tip="Tag must match ollama list exactly",
    )


def check_sandbox() -> Check:
    t0 = time.perf_counter()
    raw = (os.getenv("ETHER_SANDBOX_BACKEND") or "auto").strip().lower()
    docker = shutil.which("docker") is not None
    if raw in ("local", "subprocess", "native"):
        py = os.getenv("ETHER_SANDBOX_PYTHON") or ("python3" if sys.platform != "win32" else sys.executable)
        ok = shutil.which(py) is not None or Path(py).exists()
        return Check(
            "sandbox",
            ok,
            "critical" if not ok else "info",
            f"local · {py}",
            tip="Weaker isolation than Docker — trusted code only",
            duration_ms=_ms(t0),
        )
    if raw == "docker" or (raw == "auto" and docker):
        if not docker:
            return Check(
                "sandbox",
                False,
                "critical",
                "docker backend required but docker missing",
                tip="Install Docker or set ETHER_SANDBOX_BACKEND=local",
                duration_ms=_ms(t0),
            )
        # quick docker ping
        try:
            p = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=12,
            )
            ok = p.returncode == 0
            return Check(
                "sandbox",
                ok,
                "critical" if not ok else "info",
                "docker " + ("ok" if ok else "daemon error"),
                detail=(p.stderr or p.stdout or "")[:200],
                tip="Restart Docker Desktop if API 500",
                duration_ms=_ms(t0),
            )
        except Exception as e:
            return Check("sandbox", False, "critical", f"docker: {e}", duration_ms=_ms(t0))
    # auto without docker → local
    py = os.getenv("ETHER_SANDBOX_PYTHON") or ("python3" if sys.platform != "win32" else sys.executable)
    ok = shutil.which(py) is not None or Path(py).exists()
    return Check(
        "sandbox",
        ok,
        "critical" if not ok else "info",
        f"auto→local · {py}",
        duration_ms=_ms(t0),
    )


def check_manifest() -> Check:
    t0 = time.perf_counter()
    try:
        from core.config import load_config

        load_config()
        return Check("manifest", True, "info", "config/manifest ok", duration_ms=_ms(t0))
    except Exception as e:
        return Check("manifest", False, "high", f"manifest: {e}", duration_ms=_ms(t0))


def check_registry() -> Check:
    t0 = time.perf_counter()
    try:
        from core.registry import build_default_registry

        gems = build_default_registry().list_gems()
        need = {
            "clear-quartz",
            "rose-quartz",
            "selenite",
            "black-tourmaline",
            "grandidierite",
        }
        missing = sorted(need - set(gems))
        ok = not missing
        return Check(
            "registry",
            ok,
            "critical" if missing else "info",
            f"{len(gems)} gems" + (f" missing {missing}" if missing else ""),
            duration_ms=_ms(t0),
        )
    except Exception as e:
        return Check("registry", False, "critical", str(e), duration_ms=_ms(t0))


def check_memory_dirs() -> Check:
    t0 = time.perf_counter()
    dirs = [
        "memory/runs",
        "memory/flywheel",
        "memory/experience",
        "memory/bench",
        "memory/curriculum",
        "memory/learning",
    ]
    missing = [d for d in dirs if not (ROOT / d).exists()]
    for d in dirs:
        (ROOT / d).mkdir(parents=True, exist_ok=True)
    return Check(
        "memory_dirs",
        True,
        "low" if missing else "info",
        "ok" if not missing else f"created {missing}",
        duration_ms=_ms(t0),
    )


def check_flywheel_heartbeat() -> Check:
    t0 = time.perf_counter()
    path = ROOT / "memory" / "flywheel" / "heartbeat.txt"
    if not path.exists():
        return Check(
            "flywheel_heartbeat",
            True,
            "low",
            "no heartbeat (daemon idle)",
            tip="Normal if autonomy not running",
            duration_ms=_ms(t0),
        )
    try:
        raw = path.read_text(encoding="utf-8").strip()
        # try parse iso
        from datetime import datetime as dt

        ts = None
        for cand in (raw, raw.replace(" ", "T")):
            try:
                ts = dt.fromisoformat(cand.replace("Z", "+00:00"))
                break
            except Exception:
                continue
        if ts is None:
            return Check("flywheel_heartbeat", True, "info", f"present: {raw[:40]}", duration_ms=_ms(t0))
        age_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0
        stale = age_h > 2.0
        return Check(
            "flywheel_heartbeat",
            not stale,
            "medium" if stale else "info",
            f"age {age_h:.2f}h",
            detail=raw[:80],
            tip="Daemon may have stopped" if stale else "",
            duration_ms=_ms(t0),
        )
    except Exception as e:
        return Check("flywheel_heartbeat", False, "low", str(e), duration_ms=_ms(t0))


def check_intel_gates() -> Check:
    t0 = time.perf_counter()
    try:
        from core.health_metric import compute_health

        h = compute_health()
        reasons = h.get("unhealthy_reasons") or []
        ok = bool(h.get("healthy"))
        return Check(
            "intel_gates",
            ok,
            "high" if not ok else "info",
            "healthy" if ok else "unhealthy: " + ", ".join(reasons)[:160],
            detail=json.dumps(
                {
                    "pass_rate": h.get("pass_rate"),
                    "quiz": h.get("quiz_pass_rate"),
                    "stale": h.get("stale"),
                }
            ),
            tip="Run python scripts/weekly_scoreboard.py to refresh bench+quiz",
            duration_ms=_ms(t0),
        )
    except Exception as e:
        return Check("intel_gates", False, "medium", str(e), duration_ms=_ms(t0))


def check_sandbox_smoke() -> Check:
    """Optional live execute of trivial code (can be slow with Docker)."""
    if os.getenv("ETHER_HEALTH_SKIP_SANDBOX", "0") == "1":
        return Check("sandbox_smoke", True, "info", "skipped", tip="ETHER_HEALTH_SKIP_SANDBOX=1")
    t0 = time.perf_counter()
    try:
        from uuid import uuid4

        from core.schemas import Envelope, ClearQuartzRequest
        from gems.clear_quartz.sandbox import ClearQuartz

        res = ClearQuartz().execute(
            Envelope(
                task_id=uuid4(),
                target_gem="clear-quartz",
                payload=ClearQuartzRequest(code="print(41+1)\nassert 41+1==42\n"),
                timeout_seconds=int(os.getenv("ETHER_HEALTH_SANDBOX_TIMEOUT", "45")),
            )
        )
        if res.error:
            return Check(
                "sandbox_smoke",
                False,
                "critical",
                res.error.message[:120],
                tip=res.error.suggested_action or "",
                duration_ms=_ms(t0),
            )
        ok = res.payload is not None and res.payload.exit_code == 0
        return Check(
            "sandbox_smoke",
            ok,
            "critical" if not ok else "info",
            f"exit={getattr(res.payload, 'exit_code', '?')}",
            detail=(getattr(res.payload, "stdout", "") or "")[:80],
            duration_ms=_ms(t0),
        )
    except Exception as e:
        return Check("sandbox_smoke", False, "critical", str(e)[:160], duration_ms=_ms(t0))


def run_health_checks(*, include_sandbox_smoke: bool = True) -> Dict[str, Any]:
    checks: List[Check] = [
        check_python(),
        check_git(),
        check_ollama(),
        check_sandbox(),
        check_manifest(),
        check_registry(),
        check_memory_dirs(),
        check_flywheel_heartbeat(),
        check_intel_gates(),
    ]
    if include_sandbox_smoke:
        checks.append(check_sandbox_smoke())

    critical_fail = [c for c in checks if not c.ok and c.severity == "critical"]
    high_fail = [c for c in checks if not c.ok and c.severity == "high"]
    any_fail = [c for c in checks if not c.ok]

    if critical_fail:
        status = "critical"
    elif high_fail:
        status = "degraded"
    elif any_fail:
        status = "warn"
    else:
        status = "ok"

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "ok": status == "ok",
        "counts": {
            "total": len(checks),
            "passed": sum(1 for c in checks if c.ok),
            "failed": len(any_fail),
            "critical_failed": len(critical_fail),
        },
        "checks": [asdict(c) for c in checks],
        "tips": [c.tip for c in checks if not c.ok and c.tip],
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(report, indent=2), encoding="utf-8")
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "timestamp": report["timestamp"],
                    "status": status,
                    "failed": [c.id for c in any_fail],
                }
            )
            + "\n"
        )
    return report


def format_report(report: Dict[str, Any]) -> str:
    lines = [
        f"@ETHER health [{report.get('status')}] "
        f"{report.get('counts', {}).get('passed')}/{report.get('counts', {}).get('total')} passed",
        f"  at {report.get('timestamp')}",
    ]
    for c in report.get("checks") or []:
        mark = "✓" if c.get("ok") else "✗"
        lines.append(
            f"  {mark} {c.get('id'):20} [{c.get('severity'):8}] {c.get('message')}"
        )
        if c.get("tip") and not c.get("ok"):
            lines.append(f"      tip: {c.get('tip')}")
    return "\n".join(lines)
