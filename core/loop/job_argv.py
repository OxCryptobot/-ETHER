"""F13: allowlist pending job argv. Host still executes; this is the gate."""
from __future__ import annotations

from typing import Iterable, List

ALLOWED_BINS = frozenset(
    {
        ".venv/Scripts/python.exe",
        "python",
        "python.exe",
        "python3",
    }
)
ALLOWED_MODS = frozenset(
    {
        "pytest",
        "scripts.pep8_loop",
        "core.gem_energy",
        "core.context_budget",
        "core.latency_slo",
        "core.measure_tick",
        "core.loop.idle_refill",
        "scripts.deploy_pipeline",
    }
)
FORBIDDEN = ("rm ", "del ", "format ", "powershell", "cmd.exe", "curl ", "wget ")


def argv_ok(argv: Iterable[str]) -> bool:
    args: List[str] = [str(a) for a in argv]
    if not args:
        return False
    blob = " ".join(args).lower()
    if any(tok in blob for tok in FORBIDDEN):
        return False
    head = args[0].replace("\\", "/")
    if not any(head.endswith(b.split("/")[-1]) or head.endswith(b) or b in head for b in ALLOWED_BINS):
        return False
    if "-m" in args:
        i = args.index("-m")
        if i + 1 < len(args) and args[i + 1] not in ALLOWED_MODS and not args[i + 1].startswith("scripts."):
            return False
    return True
