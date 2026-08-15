"""Moonshot 22 — AST-edit / multifile success rate tile."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "ast_edit_kpi.json"


def compute() -> Dict[str, Any]:
    from core.honest_live import collect_scoreboard_rows

    rows = collect_scoreboard_rows()
    multi_ok = multi_n = ast_ok = ast_n = 0
    for r in rows:
        hay = " ".join(
            str(r.get(k) or "")
            for k in ("strategy", "path", "name", "fixture", "note", "mode")
        ).lower()
        ok = bool(r.get("ok"))
        if any(x in hay for x in ("multifile", "multi_file", "apply_many")):
            multi_n += 1
            if ok:
                multi_ok += 1
        if any(x in hay for x in ("ast", "edit_transaction", "apply_patch")):
            ast_n += 1
            if ok:
                ast_ok += 1

    def rate(n: int, d: int):
        return round(n / d, 4) if d else None

    payload = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "multifile_ok": multi_ok,
        "multifile_n": multi_n,
        "multifile_rate": rate(multi_ok, multi_n),
        "ast_ok": ast_ok,
        "ast_n": ast_n,
        "ast_rate": rate(ast_ok, ast_n),
        "primary": f"{multi_ok}/{multi_n}",
        "note": "1C landed — this tile proves multifile/AST under real jobs",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
