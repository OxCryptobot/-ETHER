"""One read model for the Matrix face and the exe window. Writes nothing."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
MAX_AGE_S = 6 * 3600


def _root() -> Path:
    env = os.environ.get("ETHER_ROOT")
    if env:
        return Path(env).resolve()
    return ROOT


def _read(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _stale(ts: str) -> bool:
    if not ts:
        return True
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() > MAX_AGE_S


def snapshot() -> Dict[str, Any]:
    root = _root()
    alive = _read(root / "artifacts" / "app_alive.json")
    evolve = _read(root / "artifacts" / "evolve.json")
    skills = evolve.get("skills") if isinstance(evolve.get("skills"), dict) else {}
    auditor = skills.get("super-auditor") if isinstance(skills.get("super-auditor"), dict) else {}
    goal = evolve.get("goal") if isinstance(evolve.get("goal"), dict) else {}
    ts = str(alive.get("ts") or "")
    stale = _stale(ts)
    gaps = [str(g) for g in (auditor.get("gaps") or [])]
    if stale and "app_alive_stale" not in gaps:
        gaps.append("app_alive_stale")
    learn = skills.get("learn") if isinstance(skills.get("learn"), dict) else {}
    return {
        "face": "matrix",
        "hands": "exe",
        "writer": "exe",
        "mutates": False,
        "ports": {"watch": 7843, "retired": 8787},
        "app_alive_ts": ts or None,
        "ollama": bool(alive.get("ollama")),
        "stale": stale,
        "goal": goal.get("id"),
        "generation": evolve.get("generation"),
        "walk_ok": evolve.get("walk_ok"),
        "gaps": gaps,
        "learn": learn.get("kind"),
    }


WATCH_HTML = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>ETHER</title>
<style>
:root{color-scheme:dark}
body{margin:0;background:#07080a;color:#d7dbe0;font:15px/1.45 ui-sans-serif,system-ui}
main{max-width:640px;margin:48px auto;padding:0 20px}
h1{font-size:20px;margin:0 0 8px}
p{color:#9aa3ad;margin:0 0 16px}
dl{display:grid;grid-template-columns:140px 1fr;gap:6px 12px}
dt{color:#8b939c}dd{margin:0}
.bad{color:#ef9f2e}
</style>
</head><body>
<main>
<h1>ETHER</h1>
<p>Matrix watches. The exe writes. This page does not.</p>
<dl id="rows"></dl>
</main>
<script>
async function tick(){
  const res = await fetch("/status");
  const row = await res.json();
  const keys = ["face","hands","writer","app_alive_ts","stale","ollama","goal","generation","walk_ok","gaps","learn"];
  const root = document.getElementById("rows");
  root.replaceChildren();
  for (const key of keys){
    const dt = document.createElement("dt");
    dt.textContent = key;
    const dd = document.createElement("dd");
    const val = row[key];
    dd.textContent = Array.isArray(val) ? val.join(", ") : String(val ?? "");
    if (key === "stale" && val) dd.className = "bad";
    root.append(dt, dd);
  }
}
tick();
setInterval(tick, 5000);
</script>
</body></html>
"""
