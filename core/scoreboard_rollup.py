"""Moonshot 20 — Scoreboard auto-rollup into one latest file."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "scoreboard_latest.json"


def rollup() -> Dict[str, Any]:
    from core.honest_live import collect_scoreboard_rows, classify_row

    rows = collect_scoreboard_rows()
    classified = [classify_row(r) for r in rows]
    live = [c for c in classified if c.get("live")]
    scripted = [
        c
        for c in classified
        if (c.get("mode") or "") == "scripted" or (not c.get("live"))
    ]
    honest = sum(1 for c in classified if c.get("honest"))
    live_honest = sum(1 for c in live if c.get("honest"))
    live_ok = sum(1 for c in live if c.get("ok"))
    scripted_ok = sum(1 for c in scripted if c.get("ok"))

    def rate(n: int, d: int):
        return round(n / d, 4) if d else None

    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "n_rows": len(classified),
        "honest_n": honest,
        "honest_rate": rate(honest, len(classified)),
        "live_n": len(live),
        "live_ok_n": live_ok,
        "live_honest_n": live_honest,
        "live_honest_rate": rate(live_honest, len(live)),
        "scripted_n": len(scripted),
        "scripted_ok_n": scripted_ok,
        "scripted_ok_rate": rate(scripted_ok, len(scripted)),
        "disguised_pass_n": sum(1 for c in classified if c.get("disguised_pass")),
        "results_tail": rows[:20],
        "note": "Dashboard should read this single file",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(rollup(), indent=2))
