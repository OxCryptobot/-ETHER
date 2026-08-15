"""Moonshot 15 — Speculative scripted shadow tagging (post-hoc, no parallel GPU).

Compares live vs scripted scoreboard rows by fixture/strategy key and tags
divergence as disguised_pass candidates. Safe: measurement only.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "shadow_tags.json"


def _key(row: Dict[str, Any]) -> str:
    return "|".join(
        str(row.get(k) or "")
        for k in ("fixture", "strategy", "arm", "tier", "name", "id")
    )[:120]


def compute() -> Dict[str, Any]:
    from core.honest_live import collect_scoreboard_rows, classify_row

    rows = collect_scoreboard_rows()
    scripted_ok: Dict[str, bool] = {}
    live_rows: List[Dict[str, Any]] = []
    for r in rows:
        c = classify_row(r)
        k = _key(r)
        mode = str(r.get("mode") or "").lower()
        if mode == "scripted" or (not c.get("live") and "scripted" in str(r.get("strategy") or "").lower()):
            if c.get("ok"):
                scripted_ok[k] = True
        if c.get("live"):
            live_rows.append({"row": r, "c": c, "key": k})

    tags: List[Dict[str, Any]] = []
    for item in live_rows:
        c = item["c"]
        k = item["key"]
        diverged = bool(c.get("ok") and not c.get("honest") and scripted_ok.get(k))
        if diverged or c.get("disguised_pass"):
            tags.append(
                {
                    "key": k,
                    "live_ok": c.get("ok"),
                    "honest": c.get("honest"),
                    "scripted_ok": scripted_ok.get(k),
                    "tag": "disguised_pass_candidate",
                }
            )

    payload = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "n_tags": len(tags),
        "tags": tags[:50],
        "note": "Post-hoc shadow; does not run parallel live GPU jobs",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
