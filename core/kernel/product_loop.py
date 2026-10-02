"""Tool edit, then tests. Generate-only is not a pass. Kept only if tests pass."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from core.kernel.edit_tx import EditTx
from core.kernel.honest import is_honest_tool_path_pass


def parse_edit(text: str) -> Optional[Tuple[str, str]]:
    old = new = ""
    for line in (text or "").splitlines():
        if line.startswith("OLD:"):
            old = line[4:].strip()
        elif line.startswith("NEW:"):
            new = line[4:].strip()
    if old and new and old != new:
        return old, new
    return None


def run_edit(workspace: Path, rel: str, old: str, new: str, test_fn: Callable[[], bool]) -> Dict[str, object]:
    workspace = Path(workspace)
    tx = EditTx(workspace, workspace.parent / (workspace.name + ".snap"))
    tx.begin()
    path = workspace / rel
    text = path.read_text(encoding="utf-8")
    if old not in text:
        tx.revert()
        row: Dict[str, object] = {
            "ok": False,
            "honest": False,
            "strategy": "tool_runtime",
            "mode": "live",
            "tools": ["replace_once"],
            "tests_ok": False,
            "reason": "not_found",
            "tx": list(tx.log),
        }
        return row
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    try:
        tests_ok = bool(test_fn())
    except Exception:
        tests_ok = False
    done = tx.finish(tests_ok)
    row = {
        "ok": tests_ok,
        "strategy": "tool_runtime",
        "mode": "live",
        "degraded": [],
        "tool_runtime_ok": tests_ok,
        "tools": ["replace_once"],
        "tests_ok": tests_ok,
        "tx": done["log"],
    }
    row["honest"] = is_honest_tool_path_pass(row)
    return row


def run_model_edit(
    workspace: Path,
    rel: str,
    model_text: str,
    test_fn: Callable[[], bool],
) -> Dict[str, object]:
    edit = parse_edit(model_text)
    if edit is None:
        return {
            "ok": False,
            "honest": False,
            "strategy": "generate",
            "mode": "live",
            "generate_fallback": True,
            "reason": "no_tool_edit",
            "tests_ok": False,
        }
    old, new = edit
    return run_edit(workspace, rel, old, new, test_fn)
