"""Apply a unified diff inside the repo root. Containment first."""
from __future__ import annotations
import subprocess
from pathlib import Path
from tools._lib import emit, parse_payload

ROOT = Path(__file__).resolve().parents[2]
BLOCK = {".git", ".venv", "memory", "node_modules"}

def _contained(rel: str) -> bool:
    raw = rel.replace("\\", "/").lstrip("ab/")
    if raw.startswith("/") or (len(raw) > 1 and raw[1] == ":"):
        return False
    if ".." in Path(raw).parts:
        return False
    if any(part.lower() in BLOCK for part in Path(raw).parts):
        return False
    try:
        (ROOT / raw).resolve().relative_to(ROOT.resolve())
    except (OSError, ValueError):
        return False
    return True

def main(payload):
    diff = str(payload.get("diff") or "")
    if not diff.strip():
        return {"ok": False, "error": "empty diff"}
    for line in diff.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            path = line[4:].strip()
            if path == "/dev/null":
                continue
            if not _contained(path):
                return {"ok": False, "error": f"blocked path in diff: {line}"}
    p = subprocess.run(["git", "apply", "--whitespace=nowarn", "-"], input=diff, cwd=str(ROOT), capture_output=True, text=True)
    return {"ok": p.returncode == 0, "returncode": p.returncode, "stdout": (p.stdout or "")[-500:], "stderr": (p.stderr or "")[-500:]}

if __name__ == "__main__":
    emit(main(parse_payload()))
