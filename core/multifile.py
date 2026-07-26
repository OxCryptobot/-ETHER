"""Real multi-file workflow under memory/scratch only."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / "memory" / "scratch"


def is_multifile_objective(objective: str) -> bool:
    o = (objective or "").lower()
    return bool(
        re.search(r"\b(multi[- ]?file|two files|module a|module b|refactor|package)\b", o)
        or "memory/scratch" in o
    )


def write_pair(files: Dict[str, str]) -> Dict[str, Any]:
    """Write name->content under scratch. Reject path escape."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    written = []
    for name, content in files.items():
        name = name.replace("\\", "/").lstrip("/")
        if ".." in name or name.startswith("/"):
            return {"ok": False, "error": "path escape"}
        if not name.endswith(".py"):
            name = name + ".py"
        path = SCRATCH / name
        if not str(path.resolve()).startswith(str(SCRATCH.resolve())):
            return {"ok": False, "error": "outside scratch"}
        path.write_text(content, encoding="utf-8")
        written.append(str(path.relative_to(ROOT)))
    return {"ok": True, "written": written}


def extract_file_blocks(code: str) -> Dict[str, str]:
    """Parse markers: # file: foo.py ... # file: bar.py"""
    files: Dict[str, str] = {}
    if not code:
        return files
    parts = re.split(r"(?m)^#\s*file:\s*([\w./-]+)\s*$", code)
    # parts[0] preamble, then name, body, name, body...
    if len(parts) < 3:
        return files
    it = iter(parts[1:])
    for name in it:
        body = next(it, "")
        files[name.strip()] = body.strip() + "\n"
    return files


def run_multifile_cycle(generated: str) -> Tuple[str, Dict[str, Any]]:
    """If multi-file markers present, write to scratch and build a runner string."""
    files = extract_file_blocks(generated)
    meta: Dict[str, Any] = {"multifile": bool(files)}
    if not files:
        return generated, meta
    w = write_pair(files)
    meta["write"] = w
    if not w.get("ok"):
        return generated, meta
    # Prefer test_*.py or main.py as entry
    entry = None
    for cand in ("test_main.py", "test_app.py", "main.py", "app.py"):
        if cand in files or cand in {Path(p).name for p in w.get("written") or []}:
            entry = cand
            break
    if entry is None:
        entry = Path(w["written"][0]).name
    runner = (
        f"import runpy, sys\n"
        f"sys.path.insert(0, r'{SCRATCH}')\n"
        f"runpy.run_path(r'{SCRATCH / entry}', run_name='__main__')\n"
    )
    meta["entry"] = entry
    return runner, meta
