"""Moonshot 12 — Honest-live sparkline (last 50 runs)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "honest_sparkline.json"
N = 50


def compute() -> Dict[str, Any]:
    from core.honest_live import collect_scoreboard_rows, classify_row

    rows = collect_scoreboard_rows()
    points: List[Dict[str, Any]] = []
    for r in rows[:N]:
        c = classify_row(r)
        # green only if honest tool path pass
        color = "green" if c.get("honest") else ("red" if c.get("ok") else "gray")
        points.append(
            {
                "honest": bool(c.get("honest")),
                "ok": bool(c.get("ok")),
                "live": bool(c.get("live")),
                "disguised": bool(c.get("disguised_pass")),
                "color": color,
                "mode": c.get("mode"),
            }
        )
    green = sum(1 for p in points if p["color"] == "green")
    payload = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "n": len(points),
        "green_n": green,
        "sparkline": "".join("G" if p["color"] == "green" else ("R" if p["color"] == "red" else ".") for p in points),
        "points": points,
        "note": "G=honest pass, R=ok but not honest, .=fail",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
