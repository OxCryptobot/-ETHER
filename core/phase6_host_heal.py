"""Phase 6 — host self-heal contract canary.

Verifies recovery hooks exist in host_agent without running them.
"""
from __future__ import annotations

import inspect
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "phase6_host_heal.json"

REQUIRED = (
    "git_clean_slate",
    "git_sync",
    "rehydrate_measure",
    "purge_live_pending",
    "_rotate_log_if_needed",
    "maybe_measure_tick",
)


def check() -> Dict[str, Any]:
    cases: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        cases.append({"name": name, "pass": bool(ok), "detail": detail[:100]})

    try:
        from scripts import host_agent as ha

        src = inspect.getsource(ha)
        for name in REQUIRED:
            add(f"has_{name}", name in src, name)
        add("log_not_pushed", "host_agent_log.txt" in src and "Never" in src or "LOG_MAX" in src)
    except Exception as e:
        add("import_host_agent", False, str(e))

    try:
        from core.host_health import compute as hh

        h = hh()
        add("host_health_module", "ok" in h or "alive" in h, str(h.get("alive")))
    except Exception as e:
        add("host_health_module", False, str(e))

    passed = sum(1 for c in cases if c["pass"])
    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "phase": "6",
        "n": len(cases),
        "passed": passed,
        "ok": passed == len(cases),
        "cases": cases,
        "note": "Contract presence only. Does not reset git or kill processes.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(check(), indent=2))
