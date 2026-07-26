#!/usr/bin/env python3
"""Write a temp test module and run pytest -q. No network."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import emit, read_input


def main() -> None:
    inp = read_input()
    code = inp.get("code") or ""
    tests = inp.get("tests") or ""
    if not code and not tests:
        emit(False, error="code and/or tests required")
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        (tdir / "mod.py").write_text(code or "# empty\n", encoding="utf-8")
        test_body = tests or (
            "from mod import *\n"
            "def test_importable():\n"
            "    assert True\n"
        )
        (tdir / "test_mod.py").write_text(test_body, encoding="utf-8")
        p = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--tb=line"],
            cwd=str(tdir),
            capture_output=True,
            text=True,
            timeout=int(inp.get("timeout", 60)),
        )
        emit(
            p.returncode == 0,
            returncode=p.returncode,
            stdout=(p.stdout or "")[-2000:],
            stderr=(p.stderr or "")[-1000:],
        )


if __name__ == "__main__":
    main()
