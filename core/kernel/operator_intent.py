"""Operator flag: Grok optional. Honest scoring not optional."""
from __future__ import annotations
import json, os
from pathlib import Path

def grok_required() -> bool:
    return os.getenv("ETHER_GROK_REQUIRED", "0") == "1"

def load(root: Path | None = None) -> dict:
    base = Path(root or os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[2])
    p = base / "artifacts" / "operator_intent.json"
    if not p.is_file():
        return {"grok_required": False, "honest_gate": True, "soft_launch": False}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"grok_required": False, "honest_gate": True, "soft_launch": False}
