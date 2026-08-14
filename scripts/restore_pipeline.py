"""Emergency restore core/pipeline.py from base64 part files."""
from __future__ import annotations
import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "core" / "pipeline.py"

def main() -> int:
    parts = []
    i = 0
    while True:
        p = ROOT / "artifacts" / f"pipeline_b64_part_{i}.txt"
        if not p.exists():
            break
        parts.append(p.read_text(encoding="utf-8").strip())
        i += 1
    if not parts:
        print("RESTORE ABORT: no parts found")
        return 1
    b64 = "".join(parts)
    text = base64.b64decode(b64).decode("utf-8")
    if "tool_runtime_failed_terminal" not in text or "class Pipeline:" not in text:
        print("RESTORE ABORT: invalid content")
        return 2
    OUT.write_text(text, encoding="utf-8")
    print(f"RESTORED {OUT} bytes={len(text)} parts={len(parts)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
