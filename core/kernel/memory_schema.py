"""JSONL memory rows must carry a schema version."""
from __future__ import annotations
from typing import Any, Dict

SCHEMA = "ether_mem_v1"

def stamp(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    out.setdefault("schema", SCHEMA)
    return out

def accepted(row: Dict[str, Any]) -> bool:
    return str((row or {}).get("schema") or "") == SCHEMA
