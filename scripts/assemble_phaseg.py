"""Assemble phaseG tool_runtime from b64 parts."""
from pathlib import Path
import base64
parts = []
for i in range(3):
    parts.append(Path(f"scripts/_phaseg_b64_{i}.txt").read_text(encoding="ascii").strip())
raw = base64.b64decode("".join(parts))
Path("core/tool_runtime.py").write_bytes(raw)
print("restored", len(raw))
