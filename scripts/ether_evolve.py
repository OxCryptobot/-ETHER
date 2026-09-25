"""Controlled evolution: 8 gems walk, score, template-fabricate once per real FAIL."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def _root() -> Path:
    import os
    env = os.environ.get("ETHER_ROOT")
    if env and (Path(env) / "scripts").is_dir():
        return Path(env).resolve()
    win = Path(r"C:\Users\Otcde\ETHER")
    if (win / "scripts").is_dir():
        return win.resolve()
    return Path(__file__).resolve().parents[1]


TRACE = "artifacts/self_build_trace.jsonl"


def record(row: Dict[str, Any]) -> Path:
    p = _root() / TRACE
    p.parent.mkdir(parents=True, exist_ok=True)
    row = dict(row)
    row["ts"] = datetime.now(timezone.utc).isoformat()
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str)[:3000] + "\n")
    return p


def generation() -> int:
    p = _root() / TRACE
    if not p.is_file():
        return 0
    return sum(1 for _ in p.open(encoding="utf-8"))


def _last_fail_id() -> Optional[str]:
    failed = _root() / "artifacts" / "jobs" / "failed"
    if not failed.is_dir():
        return None
    files = sorted(failed.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files:
        stem = path.stem
        if stem.startswith("medic"):
            continue
        return stem[:40]
    return None


def _prev_evolve() -> Dict[str, Any]:
    p = _root() / "artifacts" / "evolve.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _bump_energy(walk: Dict[str, Any]) -> Dict[str, Any]:
    path = _root() / "artifacts" / "gem_energy.json"
    prev: Dict[str, Any] = {}
    if path.is_file():
        try:
            prev = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            prev = {}
    n_ok = sum(1 for r in (walk.get("rows") or []) if r.get("ok"))
    row = {
        "evolve_ts": datetime.now(timezone.utc).isoformat(),
        "evolve_ok": n_ok,
        "evolve_n": int(walk.get("n") or 0),
        "generation": generation() + 1,
        "source": "ether_evolve.cycle",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**prev, **row}, indent=2) + "\n", encoding="utf-8")
    return row


def _goal(walk: Dict[str, Any]) -> Dict[str, Any]:
    """One next action. Stale 1650 writer outranks gem polish."""
    alive = _root() / "artifacts" / "app_alive.json"
    ts = ""
    if alive.is_file():
        try:
            ts = str(json.loads(alive.read_text(encoding="utf-8")).get("ts") or "")
        except Exception:
            ts = ""
    stale = True
    if ts:
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            stale = (datetime.now(timezone.utc) - dt).total_seconds() > 6 * 3600
        except Exception:
            stale = True
    if stale:
        return {
            "id": "restore_1650_writer",
            "do": "runner_register then host_main.tick",
            "why": "app_alive older than 6h and GitHub has no runner until the 1650 registers",
        }
    weak = walk.get("weak") or []
    if weak:
        return {"id": "heal_weak", "gems": [w.get("gem") for w in weak if isinstance(w, dict)]}
    return {"id": "drain_and_learn", "do": "next FAST job"}


def cycle() -> Dict[str, Any]:
    """One evolution turn. FAST-safe. Does not write host_attach."""
    from gems.protocol import GEMS
    from core.loop.gem_topo import walk_gems

    walk = walk_gems("evolve ping")
    fail_id = _last_fail_id()
    prev = _prev_evolve()
    fab: Dict[str, Any] | None = None
    if fail_id and fail_id != prev.get("fail_id"):
        try:
            import os
            os.environ["ETHER_FABRICATE_STUB_ONLY"] = "1"
            from gems.grandidierite.fabricate import fabricate
            fab = fabricate({"name": f"heal_{fail_id[:24]}", "stub_only": True, "purpose": f"heal {fail_id}"})
        except Exception as exc:
            fab = {"ok": False, "error": type(exc).__name__}
    energy = _bump_energy(walk)
    row: Dict[str, Any] = {
        "ok": bool(walk.get("n") == 8 and walk.get("ok")),
        "pillars": {
            "modular_intelligence": len(GEMS) == 8,
            "verified_execution": bool(walk.get("ok")),
            "controlled_evolution": True,
        },
        "gems": len(GEMS),
        "walk_n": walk.get("n"),
        "walk_ok": walk.get("ok"),
        "weak": walk.get("weak") or [],
        "fabricate": fab,
        "fail_id": fail_id,
        "goal": _goal(walk),
        "skills": __import__("scripts.skills", fromlist=["run_skills"]).run_skills(walk),
        "energy": energy,
        "generation": generation() + 1,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    record({"verified": row["walk_ok"], "generation": row["generation"], "fail_id": fail_id})
    out = _root() / "artifacts" / "evolve.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(row, indent=2, default=str) + "\n", encoding="utf-8")
    return row
