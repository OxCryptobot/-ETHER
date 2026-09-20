"""Host argv allowlist. Pending JSON is not an RCE bus."""
from __future__ import annotations
from pathlib import Path
from typing import Sequence

ALLOWED_TAILS = frozenset({"python.exe", "python", "pytest", "exe_pulse.py", "ether_week_tick.py", "drain_live_fifo.py", "drain_fast_fifo.py", "live_host.py", "host_tick.py"})
ALLOWED_MODS = frozenset({"pytest", "scripts.exe_pulse", "scripts.ether_week_tick", "scripts.drain_live_fifo", "scripts.live_host", "core.preference", "core.kernel.ops"})
BLOCKED = ("cmd.exe", "powershell", "pwsh", "bash", "sh", "curl", "wget", "reg.exe")

def argv_allowed(argv: Sequence[str]) -> bool:
    if not argv:
        return False
    head = Path(str(argv[0]).replace("\\", "/")).name.lower()
    if any(b in str(x).lower() for x in argv for b in BLOCKED):
        return False
    if head in {"python.exe", "python", "py"}:
        joined = " ".join(str(x) for x in argv[1:])
        if "-c" in argv:
            return "scripts." in joined or "core." in joined or "pytest" in joined
        if "-m" in argv:
            try:
                i = list(argv).index("-m")
                mod = str(argv[i + 1])
            except (ValueError, IndexError):
                return False
            return mod in ALLOWED_MODS or mod.startswith("scripts.") or mod.startswith("core.")
        tail = Path(str(argv[-1]).replace("\\", "/")).name
        return tail in ALLOWED_TAILS or tail.endswith(".py")
    return head in ALLOWED_TAILS
