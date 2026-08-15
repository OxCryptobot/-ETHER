"""Moonshot 24 — Hot-path microbench (~30s). Freeze STEADY if red."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "microbench.json"
FREEZE = ROOT / "artifacts" / "steady_frozen.json"


def run() -> Dict[str, Any]:
    steps: List[Dict[str, Any]] = []
    ok = True

    t0 = time.perf_counter()
    try:
        from core.pipeline import Pipeline  # noqa: F401

        steps.append({"name": "import_pipeline", "ok": True, "ms": round((time.perf_counter() - t0) * 1000, 1)})
    except Exception as e:
        ok = False
        steps.append({"name": "import_pipeline", "ok": False, "error": str(e)[:120]})

    t1 = time.perf_counter()
    try:
        from core.tool_runtime import TOOL_SPECS

        assert TOOL_SPECS
        steps.append(
            {
                "name": "tool_runtime_specs",
                "ok": True,
                "n": len(TOOL_SPECS),
                "ms": round((time.perf_counter() - t1) * 1000, 1),
            }
        )
    except Exception as e:
        ok = False
        steps.append({"name": "tool_runtime_specs", "ok": False, "error": str(e)[:120]})

    t2 = time.perf_counter()
    try:
        from core.measure_tick import run as measure_run

        m = measure_run()
        steps.append(
            {
                "name": "measure_tick",
                "ok": bool(m.get("ok")),
                "ms": round((time.perf_counter() - t2) * 1000, 1),
            }
        )
        if not m.get("ok"):
            ok = False
    except Exception as e:
        ok = False
        steps.append({"name": "measure_tick", "ok": False, "error": str(e)[:120]})

    payload = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "total_ms": round((time.perf_counter() - t0) * 1000, 1),
        "steps": steps,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if not ok:
        FREEZE.write_text(
            json.dumps(
                {
                    "frozen": True,
                    "reason": "microbench_red",
                    "updated": payload["updated"],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    elif FREEZE.exists():
        try:
            FREEZE.unlink()
        except Exception:
            pass

    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    payload["steady_frozen"] = FREEZE.exists()
    return payload


def is_steady_frozen() -> bool:
    return FREEZE.exists()


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
