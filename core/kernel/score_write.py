"""Single scoreboard insert. Generate rows cannot land as PASS."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from core.kernel.honest import reject_generate_pass

def write_result(path: Path, result: Dict[str, Any]) -> Dict[str, Any]:
    row = reject_generate_pass(dict(result))
    row.setdefault("schema", "ether_score_v1")
    row.setdefault("ts", datetime.now(timezone.utc).isoformat())
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    return row
