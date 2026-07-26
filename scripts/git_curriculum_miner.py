#!/usr/bin/env python3
"""Mine local git history for small pure-ish Python functions → curriculum tasks."""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "memory" / "curriculum" / "mined_tasks.json"


def run_git(*args: str) -> str:
    p = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True)
    return p.stdout or ""


def extract_functions(source: str) -> List[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    out = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            if len(node.body) > 12:
                continue
            seg = ast.get_source_segment(source, node)
            if seg and 40 < len(seg) < 800:
                out.append(seg)
    return out


def main() -> int:
    files = run_git("ls-files", "*.py").splitlines()
    tasks = []
    for rel in files[:80]:
        if any(x in rel for x in (".venv", "tests/", "memory/")):
            continue
        path = ROOT / rel
        if not path.exists():
            continue
        try:
            src = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for i, fn in enumerate(extract_functions(src)):
            name_m = re.search(r"def\s+(\w+)", fn)
            name = name_m.group(1) if name_m else f"fn{i}"
            obj = (
                f"Write only Python implementing this function, then call a simple example with print:\n"
                f"{fn}\n"
            )
            tasks.append(
                {
                    "id": f"mined_{name}_{len(tasks)}",
                    "title": name,
                    "source": rel,
                    "objective": obj[:1500],
                }
            )
            if len(tasks) >= 40:
                break
        if len(tasks) >= 40:
            break

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"tasks": tasks, "n": len(tasks)}, indent=2), encoding="utf-8")
    print(json.dumps({"mined": len(tasks), "path": str(OUT)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
