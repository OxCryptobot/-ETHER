#!/usr/bin/env python3
"""Mine small pure-ish Python commits into curriculum items (private on-distribution data)."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "memory" / "curriculum" / "mined_tasks.json"


def main() -> int:
    try:
        log = subprocess.check_output(
            ["git", "log", "--pretty=format:%H", "-n", "80"],
            cwd=str(ROOT),
            text=True,
        )
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1

    tasks = []
    for sha in log.splitlines()[:40]:
        try:
            show = subprocess.check_output(
                ["git", "show", f"{sha}:", "--name-only", "--pretty=format:"],
                cwd=str(ROOT),
                text=True,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            continue
        py_files = [ln.strip() for ln in show.splitlines() if ln.strip().endswith(".py")]
        py_files = [f for f in py_files if f.startswith(("core/", "scripts/", "gems/")) and "test" not in f]
        if not py_files or len(py_files) > 3:
            continue
        f0 = py_files[0]
        try:
            blob = subprocess.check_output(
                ["git", "show", f"{sha}:{f0}"],
                cwd=str(ROOT),
                text=True,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            continue
        # extract short pure functions
        for m in re.finditer(r"^def (\w+)\(([^)]*)\):\n((?:[ \t].*\n)+)", blob, re.M):
            name, args, body = m.group(1), m.group(2), m.group(3)
            if name.startswith("_"):
                continue
            if len(body) > 400:
                continue
            if any(k in body for k in ("open(", "subprocess", "requests", "Path(")):
                continue
            src = f"def {name}({args}):\n{body}"
            tasks.append(
                {
                    "id": f"mine_{sha[:8]}_{name}",
                    "title": f"mined:{name}",
                    "objective": (
                        f"Write only Python implementing this behavior (from local history pattern).\n"
                        f"Include asserts that exercise {name}.\n"
                        f"Reference shape:\n{src[:500]}"
                    ),
                }
            )
            if len(tasks) >= 25:
                break
        if len(tasks) >= 25:
            break

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "n": len(tasks),
        "tasks": tasks,
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "n": len(tasks), "path": str(OUT)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
