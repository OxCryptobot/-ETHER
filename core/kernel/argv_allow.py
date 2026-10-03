"""Host argv allowlist. Pending JSON is not an RCE bus."""
from __future__ import annotations
from pathlib import Path
from typing import Sequence

ALLOWED_MODS = frozenset({"pytest", "scripts.live_edit_tx"})
BLOCKED = ("cmd.exe", "powershell", "pwsh", "bash", "sh", "curl", "wget", "reg.exe")

def argv_allowed(argv: Sequence[str]) -> bool:
    if not argv or "-c" in argv:
        return False
    if any(b in str(x).lower() for x in argv for b in BLOCKED):
        return False
    head = Path(str(argv[0]).replace("\\", "/")).name.lower()
    if head not in {"python.exe", "python", "py"}:
        return False
    if "-m" not in argv:
        return False
    try:
        mod = str(list(argv)[list(argv).index("-m") + 1])
    except (ValueError, IndexError):
        return False
    return mod in ALLOWED_MODS
