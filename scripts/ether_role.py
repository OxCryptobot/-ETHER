"""ETHER role: self-build a local-LLM Cowork desktop."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from scripts.ether_cowork import deliver, run_task, schedule


def _root() -> Path:
    import os
    env = os.environ.get("ETHER_ROOT")
    if env and (Path(env) / "scripts").is_dir():
        return Path(env).resolve()
    win = Path(r"C:\Users\Otcde\ETHER")
    if (win / "scripts").is_dir():
        return win.resolve()
    return Path(__file__).resolve().parents[1]


ROLE = "self_build_cowork"


def _parse_patch(text: str) -> Dict[str, str] | None:
    path = old = new = ""
    for line in (text or "").splitlines():
        if line.startswith("PATH:"):
            path = line[5:].strip()
        elif line.startswith("OLD:"):
            old = line[4:].strip()
        elif line.startswith("NEW:"):
            new = line[4:].strip()
    if path.startswith("artifacts/") and old and new:
        return {"path": path, "old": old, "new": new}
    return None


def tick() -> Dict[str, Any]:
    """Local-LLM self-build turn. Grok is not called."""
    from scripts.ether_app import ask_model, edit_file, verify
    from scripts.ether_tools import preview_replace

    prompt = (
        "You are ETHER on this PC. Propose ONE safe file edit.\n"
        "Reply with exactly three lines:\n"
        "PATH: artifacts/self_build_note.txt\n"
        "OLD: x\n"
        "NEW: y\n"
        "Only artifacts/ paths."
    )
    idea = ask_model(prompt)
    patch = _parse_patch(idea)
    applied = {"ok": False, "reason": "no_parse_or_ollama_down"}
    note = _root() / "artifacts" / "self_build_note.txt"
    note.parent.mkdir(parents=True, exist_ok=True)
    if not note.is_file():
        note.write_text("seed\n", encoding="utf-8")
    if patch:
        preview = preview_replace(patch["path"], patch["old"], patch["new"])
        if preview.get("ok"):
            applied = edit_file(patch["path"], patch["old"], patch["new"])
        else:
            applied = {"ok": False, "preview": preview}
    elif "ollama down" not in idea.lower() and idea.strip():
        note.write_text(idea[:2000], encoding="utf-8")
        applied = {"ok": True, "path": "artifacts/self_build_note.txt", "mode": "write_idea"}
    proof = verify()
    out = run_task("self-build cowork local LLM")
    doc = deliver("self_build_plan", "local model:\n" + idea[:1500])
    schedule("self-build cowork local LLM", 60)
    row = {
        "role": ROLE,
        "ok": bool(applied.get("ok") or proof.get("ok")),
        "backend": "ollama_local",
        "idea": idea[:500],
        "applied": applied,
        "verified": proof.get("ok"),
        "plan": doc.get("path"),
        "task": out,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    stamp = _root() / "artifacts" / "self_build_role.json"
    stamp.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    return row
