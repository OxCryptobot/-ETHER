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
    starts = [i for i, line in enumerate(lines) if line.startswith("def ")]
    if not starts:
        return None
    start = starts[-1]
    body = []
    for line in lines[start:]:
        if body and line and not line[0].isspace() and not line.startswith("#"):
            break
        body.append(line.rstrip())
    src = "\n".join(body).strip() + "\n"
    if "return " not in src:
        return None
    try:
        compile(src, "<edit>", "exec")
    except SyntaxError:
        return None
    return src


def extract_functions(text: str) -> Dict[str, str]:
    """Every complete function in the reply, by name. The last one wins."""
    raw = (text or "").replace("```python", "").replace("```", "")
    lines = raw.splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith("def ")]
    found: Dict[str, str] = {}
    for start in starts:
        body = []
        for line in lines[start:]:
            if body and line and not line[0].isspace() and not line.startswith("#"):
                break
            body.append(line.rstrip())
        src = "\n".join(body).strip() + "\n"
        if "return " not in src:
            continue
        try:
            compile(src, "<edit>", "exec")
        except SyntaxError:
            continue
        name = lines[start][4:].split("(", 1)[0].strip()
        if name:
            found[name] = src
    return found


def files_from_reply(text: str, parts: Dict[str, str]) -> Optional[Dict[str, str]]:
    """Map each required function onto its file. Missing one function writes nothing."""
    found = extract_functions(text)
    mapping: Dict[str, str] = {}
    for fn, rel in parts.items():
        src = found.get(fn)
        if not src:
            return None
        mapping[str(rel)] = src
    return mapping if len(mapping) >= 2 else None


def run_files_edit(
    workspace: Path,
    files: Dict[str, str],
    test_fn: Callable[[], bool],
) -> Dict[str, object]:
    """One snapshot, then every file, then one test. A failure restores all of them."""
    workspace = Path(workspace)
    if len(files) < 2:
        return {
            "ok": False,
            "honest": False,
            "strategy": "tool_runtime",
            "mode": "live",
            "reason": "one_file",
            "tests_ok": False,
            "tools": [],
        }
    tx = EditTx(workspace, workspace.parent / (workspace.name + ".snap"))
    tx.begin()
    for rel, src in files.items():
        path = workspace / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(src, encoding="utf-8")
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
        "tools": ["replace_file"] * len(files),
        "files": list(files),
        "tests_ok": tests_ok,
        "tx": done["log"],
    }
    row["honest"] = is_honest_tool_path_pass(row)
    return row


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


def apply_reply(
    workspace: Path,
    rel: str,
    model_text: str,
    test_fn: Callable[[], bool],
    parts: Optional[Dict[str, str]] = None,
) -> Dict[str, object]:
    if parts:
        mapping = files_from_reply(model_text, parts)
        if mapping is None:
            return {
                "ok": False,
                "honest": False,
                "strategy": "generate",
                "mode": "live",
                "generate_fallback": True,
                "reason": "no_tool_edit",
                "tests_ok": False,
            }
        return run_files_edit(workspace, mapping, test_fn)
    return run_model_edit(workspace, rel, model_text, test_fn)
