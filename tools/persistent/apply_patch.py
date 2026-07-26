"""Apply a unified diff to the repo (restricted paths) then return status."""
from __future__ import annotations

import subprocess
from pathlib import Path

from tools._lib import emit, parse_payload

ROOT = Path(__file__).resolve().parents[2]
BLOCK = {".git", ".venv", "memory", "node_modules"}


def main(payload):
    diff = str(payload.get("diff") or "")
    if not diff.strip():
        return {"ok": False, "error": "empty diff"}
    # safety: reject diffs that touch blocked path segments
    for line in diff.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            low = line.lower()
            if any(b in low for b in BLOCK):
                return {"ok": False, "error": f"blocked path in diff: {line}"}
    p = subprocess.run(
        ["git", "apply", "--whitespace=nowarn", "-"],
        input=diff,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    return {
        "ok": p.returncode == 0,
        "returncode": p.returncode,
        "stdout": (p.stdout or "")[-500:],
        "stderr": (p.stderr or "")[-500:],
    }


if __name__ == "__main__":
    emit(main(parse_payload()))
