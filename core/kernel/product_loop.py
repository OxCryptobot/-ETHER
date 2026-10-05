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


def extract_function(text: str) -> Optional[str]:
    """A complete function, if the reply has one. Truncated code is not an edit."""
    raw = (text or "").replace("```python", "").replace("```", "")
    lines = raw.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("def ")), None)
    if start is None:
        return None
    body = []
    for line in lines[start:]:
        if body and line and not line[0].isspace() and not line.startswith("#"):
            break
        body.append(line.rstrip())
    src = "\n".join(body).strip() + "\n"
    if src.count("def ") != 1 or "return " not in src:
        return None
    try:
        compile(src, "<edit>", "exec")
    except SyntaxError:
        return None
    return src


def run_file_edit(workspace: Path, rel: str, new_src: str, test_fn: Callable[[], bool]) -> Dict[str, object]:
    workspace = Path(workspace)
    tx = EditTx(workspace, workspace.parent / (workspace.name + ".snap"))
    tx.begin()
    (workspace / rel).write_text(new_src, encoding="utf-8")
    try:
        tests_ok = bool(test_fn())
    except Exception:
        tests_ok = False
    done = tx.finish(tests_ok)
    row: Dict[str, object] = {
        "ok": tests_ok,
        "strategy": "tool_runtime",
        "mode": "live",
        "degraded": [],
        "tool_runtime_ok": tests_ok,
        "tools": ["replace_file"],
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
    if edit is not None:
        old, new = edit
        return run_edit(workspace, rel, old, new, test_fn)
    src = extract_function(model_text)
    if src is None:
        return {
            "ok": False,
            "honest": False,
            "strategy": "generate",
            "mode": "live",
            "generate_fallback": True,
            "reason": "no_tool_edit",
            "tests_ok": False,
        }
    return run_file_edit(workspace, rel, src, test_fn)
