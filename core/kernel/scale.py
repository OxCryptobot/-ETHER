"""Phases 3, 6, and 7. One writer. The checker cannot touch source."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def _load(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def check(row: Dict[str, Any]) -> Dict[str, Any]:
    """Read the edit result. This function does not write."""
    return {
        "gem": "clear_quartz",
        "writes": 0,
        "ok": bool(row.get("honest")) and bool(row.get("tests_ok")),
        "skipped": not bool(row.get("honest")),
    }


def second_look(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    stamps: List[str] = []
    for item in history:
        ts = str(item.get("ts") or "")
        if ts and ts not in stamps:
            stamps.append(ts)
    open_ = len(stamps) >= 2
    return {
        "open": open_,
        "writes": 0,
        "stream": False,
        "cross_repo": False,
        "worker": "read_only" if open_ else "closed",
        "n": len(stamps),
    }


def advance(root: Path) -> Dict[str, Any]:
    root = Path(root)
    art = root / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    edit = _load(art / "live_edit_tx.json")
    hist_path = art / "honest_history.json"
    hist = _load(hist_path)
    items = list(hist.get("items") or [])
    if edit.get("honest") and edit.get("ts") and not any(i.get("ts") == edit.get("ts") for i in items):
        items.append({"ts": edit.get("ts"), "honest": True})
    hist_path.write_text(json.dumps({"items": items}, indent=2) + "\n", encoding="utf-8")
    held = edit.get("note") == "curriculum_hold"
    prior = any(bool(i.get("honest")) for i in items)
    verdict = check(edit)
    if held:
        verdict = {"gem": "clear_quartz", "writes": 0, "ok": prior, "skipped": True, "note": "curriculum_hold"}
    look = second_look(items)
    (art / "gem_check.json").write_text(json.dumps(verdict, indent=2) + "\n", encoding="utf-8")
    row = {
        "ok": True,
        "held": held,
        "honest": prior if held else bool(edit.get("honest")),
        "repeatable": look["open"],
        "checker": verdict,
        "second_look": look,
    }
    (art / "scale.json").write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    return row
