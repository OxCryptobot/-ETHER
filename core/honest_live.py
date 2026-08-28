"""Honest live tool-path rates — soft-launch measurement, not theatre.

Scans scoreboard JSON rows and applies is_honest_tool_path_pass.
Writes artifacts/honest_live_rates.json for Control Matrix + STATUS.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "honest_live_rates.json"


def _load_rows(path: Path) -> List[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        results = data.get("results")
        if isinstance(results, list):
            return [r for r in results if isinstance(r, dict)]
        # single envelope
        if "ok" in data or "strategy" in data:
            return [data]
    return []


def collect_scoreboard_rows(art: Optional[Path] = None) -> List[Dict[str, Any]]:
    art = art or (ROOT / "artifacts")
    rows: List[Dict[str, Any]] = []
    if not art.exists():
        return rows
    for p in sorted(art.glob("scoreboard*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        loaded = _load_rows(p)
        mtime = p.stat().st_mtime
        for row in loaded:
            tagged = dict(row)
            tagged.setdefault("_src", p.name)
            tagged.setdefault("_mtime", mtime)
            rows.append(tagged)
        if len(rows) >= 2500:
            break
    # also memory/bench latest if present
    for rel in (
        "memory/bench/latest.json",
        "memory/quiz/latest.json",
        "memory/ledger/latest.json",
    ):
        p = ROOT / rel
        if p.exists():
            rows.extend(_load_rows(p))
    return rows[:2500]


def classify_row(row: Dict[str, Any]) -> Dict[str, Any]:
    from core.loop.handlers.tool_runtime_gate import is_honest_tool_path_pass

    mode = str(row.get("mode") or "").lower()
    strategy = str(row.get("strategy") or "").lower()
    ok = bool(row.get("ok"))
    honest = is_honest_tool_path_pass(row) if ok else False
    live = mode == "live" or "live" in strategy
    toolish = (
        "tool_runtime" in strategy
        or row.get("tool_path") is True
        or "tool_runtime" in str(row.get("path") or "").lower()
    )
    return {
        "ok": ok,
        "honest": honest,
        "live": live,
        "toolish": toolish,
        "mode": mode or None,
        "strategy": strategy or None,
        "disguised_pass": bool(ok and not honest),
    }


def compute_rates(rows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    rows = rows if rows is not None else collect_scoreboard_rows()
    classified = [classify_row(r) for r in rows]
    n = len(classified)
    ok_n = sum(1 for c in classified if c["ok"])
    honest_n = sum(1 for c in classified if c["honest"])
    live_rows = [c for c in classified if c["live"]]
    live_ok = sum(1 for c in live_rows if c["ok"])
    live_honest = sum(1 for c in live_rows if c["honest"])
    disguised = sum(1 for c in classified if c["disguised_pass"])
    tool_live = [c for c in live_rows if c["toolish"] or c["honest"]]

    def rate(num: int, den: int) -> Optional[float]:
        if den <= 0:
            return None
        return round(num / den, 4)

    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "n_rows": n,
        "ok_n": ok_n,
        "honest_pass_n": honest_n,
        "honest_pass_rate": rate(honest_n, n),
        "live_n": len(live_rows),
        "live_ok_n": live_ok,
        "live_honest_n": live_honest,
        "live_honest_rate": rate(live_honest, len(live_rows)),
        "live_ok_honest_rate": rate(live_honest, live_ok) if live_ok else None,
        "disguised_pass_n": disguised,
        "disguised_pass_rate": rate(disguised, max(1, ok_n)),
        "tool_live_n": len(tool_live),
        "soft_launch_blocked": True,
        "gate": "is_honest_tool_path_pass",
        "note": (
            "Soft launch stays blocked until live_honest_rate is measured on "
            "expanded hard suite and meets threshold. Zero live rows => unknown, not green."
        ),
    }
    # Explicit unknown vs green
    if payload["live_n"] == 0:
        payload["status"] = "no_live_rows"
        payload["soft_launch_blocked"] = True
    elif payload["live_honest_n"] == 0 and live_ok > 0:
        payload["status"] = "live_ok_but_not_honest"
        payload["soft_launch_blocked"] = True
    elif payload["live_honest_rate"] is not None and payload["live_honest_rate"] >= 0.99:
        payload["status"] = "honest_live_green"
        # still blocked until human/mentor lifts wheels — measurement only
        payload["soft_launch_blocked"] = True
        payload["note"] = (
            "Rates green on scanned rows; soft launch still requires mentor "
            "sign-off + expanded hard suite publication."
        )
    else:
        payload["status"] = "measuring"
        payload["soft_launch_blocked"] = True
    return payload


def publish(path: Optional[Path] = None) -> Dict[str, Any]:
    path = path or OUT
    payload = compute_rates()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(publish(), indent=2))
