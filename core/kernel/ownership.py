"""Which process may write which artifact."""
from __future__ import annotations
from typing import Dict

OWNERS: Dict[str, str] = {
    "artifacts/host_attach.json": "exe",
    "artifacts/app_alive.json": "exe",
    "artifacts/ollama_probe.json": "exe",
    "artifacts/exe_pulse.json": "exe",
    "artifacts/git_push.json": "exe",
    "artifacts/host_main.json": "exe",
    "artifacts/exe_loop.json": "exe",
    "artifacts/self_heal.json": "exe",
    "artifacts/exe_writer.json": "exe",
    "artifacts/kernel_events.jsonl": "exe",
    "artifacts/jobs/pending/": "enqueue",
    "artifacts/jobs/done/": "exe_or_fast",
    "artifacts/jobs/failed/": "exe_or_fast",
    "artifacts/host_agent_status.json": "fast_or_exe",
    "artifacts/gem_energy.json": "fast_or_exe",
}

def owner_of(rel: str) -> str:
    rel = rel.replace("\\", "/")
    if rel in OWNERS:
        return OWNERS[rel]
    for prefix, who in OWNERS.items():
        if prefix.endswith("/") and rel.startswith(prefix):
            return who
    return "unknown"

def may_write(rel: str, *, writer: str) -> bool:
    who = owner_of(rel)
    if who == "exe":
        return writer == "exe"
    if who in {"exe_or_fast", "fast_or_exe"}:
        return writer in {"exe", "fast", "matrix-worker"}
    if who == "enqueue":
        return writer in {"exe", "grok", "enqueue"}
    return False
