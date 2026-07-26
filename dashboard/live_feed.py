"""Build a live event stream for the Control Matrix CLI console."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]


def _git_log(n: int = 12) -> List[Dict[str, Any]]:
    try:
        p = subprocess.run(
            ["git", "log", f"-{n}", "--pretty=format:%h|%ci|%s"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=8,
        )
        rows = []
        for line in (p.stdout or "").splitlines():
            parts = line.split("|", 2)
            if len(parts) == 3:
                rows.append({"kind": "git", "hash": parts[0], "ts": parts[1], "msg": parts[2]})
        return rows
    except Exception:
        return []


def _read_json(path: Path) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def build_console(snapshot_bits: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Return console lines + code preview for the live CLI panel."""
    lines: List[Dict[str, str]] = []
    now = datetime.now(timezone.utc).isoformat()

    # in-progress
    prog = _read_json(ROOT / "memory" / "runs" / "in_progress.json")
    if prog:
        lines.append(
            {
                "ts": prog.get("updated_at") or now,
                "level": "live",
                "text": f"▶ STAGE {prog.get('stage')} · {prog.get('objective', '')[:80]}",
            }
        )
        if prog.get("detail"):
            lines.append({"ts": now, "level": "info", "text": f"  detail: {prog.get('detail')}"})

    # flywheel latest
    latest = _read_json(ROOT / "memory" / "flywheel" / "latest.json") or {}
    if latest:
        g = latest.get("gates") or {}
        ok = latest.get("ok")
        lines.append(
            {
                "ts": latest.get("timestamp") or now,
                "level": "ok" if ok else "err",
                "text": (
                    f"⚙ flywheel {'PASS' if ok else 'FAIL'} "
                    f"conf={g.get('confidence')} pull={g.get('pull_ok')} "
                    f"reason={g.get('agentic_reason')}"
                ),
            }
        )
        for name, step in (latest.get("steps") or {}).items():
            flag = "OK" if step.get("ok") else "FAIL"
            ms = int((step.get("duration_s") or 0) * 1000)
            brief = step.get("error_brief") or step.get("healed") or ""
            lines.append(
                {
                    "ts": latest.get("timestamp") or now,
                    "level": "ok" if step.get("ok") else "warn",
                    "text": f"  [{flag}] {name} {ms}ms {brief}".strip(),
                }
            )

    # latest pipeline run code + stdout
    runs_dir = ROOT / "memory" / "runs"
    code_preview = ""
    sandbox_out = ""
    sandbox_err = ""
    if runs_dir.exists():
        files = sorted(
            [p for p in runs_dir.glob("*.json") if p.name != "in_progress.json"],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if files:
            run = _read_json(files[0]) or {}
            code_preview = (run.get("generated_code") or "")[:4000]
            sand = run.get("sandbox") or {}
            if isinstance(sand, dict):
                sandbox_out = (sand.get("stdout") or "")[:2000]
                sandbox_err = (sand.get("stderr") or "")[:2000]
            lines.append(
                {
                    "ts": run.get("finished_at") or run.get("started_at") or now,
                    "level": "ok" if run.get("status") == "complete" else "err",
                    "text": (
                        f"λ run {run.get('status')} conf={run.get('confidence')} "
                        f"strategy={run.get('strategy')} chars={len(code_preview)}"
                    ),
                }
            )
            for st in run.get("stages") or []:
                lines.append(
                    {
                        "ts": now,
                        "level": "ok" if st.get("success") else "err",
                        "text": (
                            f"  · {st.get('stage')} "
                            f"{'✓' if st.get('success') else '✗'} "
                            f"{st.get('detail', '')} "
                            f"{round(float(st.get('duration_ms') or 0))}ms"
                        ),
                    }
                )

    # git
    for g in _git_log(8):
        lines.append(
            {
                "ts": g.get("ts") or now,
                "level": "git",
                "text": f"⌥ {g.get('hash')} {g.get('msg')}",
            }
        )

    # heartbeat
    hb = ""
    try:
        hb = (ROOT / "memory" / "flywheel" / "heartbeat.txt").read_text(encoding="utf-8").strip()
    except Exception:
        pass
    if hb:
        lines.append({"ts": hb, "level": "info", "text": f"♥ heartbeat {hb}"})

    # newest first, cap
    lines = lines[:80]
    return {
        "lines": lines,
        "code_preview": code_preview,
        "sandbox_stdout": sandbox_out,
        "sandbox_stderr": sandbox_err,
        "generated_at": now,
        "active": bool(prog),
    }
