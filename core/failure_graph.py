"""Failure memory graph — cluster stderr signatures to repair templates."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from core.repair import classify_stderr

ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = ROOT / "memory" / "experience" / "failure_graph.json"

# Keys MUST match the `kind` values produced by core.repair.classify_stderr.
# They used to be short forms ("syntax", "name", ...) while classify_stderr
# returns exception class names ("SyntaxError", "NameError", ...), so every
# lookup missed and every failure got the generic runtime template — the whole
# table was unreachable.
TEMPLATES = {
    "SyntaxError": "Fix SyntaxError/IndentationError. Output valid Python only, no markdown.",
    "NameError": "NameError: define missing names or fix typos before use.",
    "ImportError": "ImportError: remove third-party imports; stdlib only in sandbox.",
    "AssertionError": "AssertionError: align logic with asserts or fix expected values.",
    "TypeError": "TypeError: check None, argument counts, and operand types.",
    "ValueError": "ValueError: handle edge cases (empty, zero, None) and bad literals.",
    "Timeout": "Timeout: remove infinite loops; bound iterations.",
    "runtime": "Runtime error: read stderr and make the smallest correct fix.",
}

# Short forms written by older graph files / callers.
_ALIASES = {
    "syntax": "SyntaxError",
    "indentation": "SyntaxError",
    "name": "NameError",
    "import": "ImportError",
    "module": "ImportError",
    "assert": "AssertionError",
    "assertion": "AssertionError",
    "type": "TypeError",
    "value": "ValueError",
    "timeout": "Timeout",
}


def template_for(kind: str) -> str:
    """Template for a classify_stderr kind (or a legacy short form)."""
    k = (kind or "").strip()
    if k in TEMPLATES:
        return TEMPLATES[k]
    return TEMPLATES.get(_ALIASES.get(k.lower(), ""), TEMPLATES["runtime"])


def _sig(stderr: str) -> str:
    info = classify_stderr(stderr)
    kind = info["kind"]
    # collapse paths/numbers for clustering
    body = re.sub(r"0x[0-9a-f]+", "HEX", (stderr or "")[:300], flags=re.I)
    body = re.sub(r"\d+", "N", body)
    body = re.sub(r"[A-Za-z]:\\[^\n]+", "PATH", body)
    line = body.strip().splitlines()[-1] if body.strip() else kind
    return f"{kind}::{line[:120]}"


def _load() -> Dict[str, Any]:
    if not GRAPH_PATH.exists():
        return {"nodes": {}}
    try:
        return json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"nodes": {}}


def _save(data: Dict[str, Any]) -> None:
    GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    GRAPH_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def observe(stderr: str, repaired_ok: bool = False) -> Dict[str, Any]:
    sig = _sig(stderr)
    kind = classify_stderr(stderr)["kind"]
    data = _load()
    nodes = data.setdefault("nodes", {})
    node = nodes.get(sig) or {
        "kind": kind,
        "count": 0,
        "repaired_ok": 0,
    }
    node["kind"] = node.get("kind") or kind
    # refresh: nodes persisted before the key alignment carry the generic
    # runtime template baked in, which would otherwise stick forever
    node["template"] = template_for(node["kind"])
    node["count"] = int(node.get("count") or 0) + 1
    if repaired_ok:
        node["repaired_ok"] = int(node.get("repaired_ok") or 0) + 1
    node["last_seen"] = datetime.now(timezone.utc).isoformat()
    nodes[sig] = node
    # keep graph bounded
    if len(nodes) > 300:
        ordered = sorted(nodes.items(), key=lambda kv: kv[1].get("last_seen") or "")
        data["nodes"] = dict(ordered[-300:])
    _save(data)
    return {"signature": sig, **node}


def repair_hint(stderr_or_kind: str) -> str:
    """Repair template for a stderr blob OR a bare failure kind.

    `core.experience.retrieve` calls this with a kind string ("SyntaxError"),
    not stderr, so both are accepted explicitly instead of relying on the
    substring match in classify_stderr.
    """
    text = (stderr_or_kind or "").strip()
    if text in TEMPLATES or text.lower() in _ALIASES:
        return template_for(text)
    sig = _sig(text)
    data = _load()
    node = (data.get("nodes") or {}).get(sig)
    if node:
        return template_for(node.get("kind") or classify_stderr(text)["kind"])
    return template_for(classify_stderr(text)["kind"])


def top_failures(n: int = 10) -> List[Dict[str, Any]]:
    data = _load()
    nodes = data.get("nodes") or {}
    ranked = sorted(nodes.items(), key=lambda kv: int(kv[1].get("count") or 0), reverse=True)
    return [{"signature": k, **v} for k, v in ranked[:n]]
