"""grep, glob, surgical patch, rollback, rename, delete — kernel wrap."""
from __future__ import annotations
import re
from pathlib import Path
from typing import Any, Dict, List

def _ws(rt: Any) -> Path | None:
    ws = getattr(rt, "workspace", None)
    return Path(ws) if ws is not None else None

def grep(rt: Any, pattern: str, path: str = "") -> Dict[str, Any]:
    ws = _ws(rt)
    if ws is None:
        return {"ok": False, "error": "no_workspace"}
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        return {"ok": False, "error": f"bad_regex:{exc}"}
    root = ws / path if path else ws
    hits: List[str] = []
    files = [root] if root.is_file() else list(root.rglob("*"))[:200]
    for p in files:
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                rel = str(p.relative_to(ws)).replace("\\", "/")
                hits.append(f"{rel}:{i}:{line.strip()[:160]}")
                if len(hits) >= 40:
                    return {"ok": True, "hits": hits, "n": len(hits), "capped": True}
    return {"ok": True, "hits": hits, "n": len(hits)}

def glob_files(rt: Any, pattern: str) -> Dict[str, Any]:
    ws = _ws(rt)
    if ws is None:
        return {"ok": False, "error": "no_workspace"}
    files = [str(p.relative_to(ws)).replace("\\", "/") for p in ws.glob(pattern or "**/*.py") if p.is_file()][:80]
    return {"ok": True, "files": files, "n": len(files)}

def apply_patch(rt: Any, path: str, old: str, new: str) -> Dict[str, Any]:
    ws = _ws(rt)
    if ws is None:
        return {"ok": False, "error": "no_workspace"}
    from core.kernel.secret_scan import secret_hit
    hit = secret_hit(new)
    if hit:
        return {"ok": False, "error": hit}
    target = (ws / path).resolve()
    try:
        target.relative_to(ws.resolve())
    except ValueError:
        return {"ok": False, "error": "path_escape"}
    if not target.is_file():
        return {"ok": False, "error": f"not found: {path}"}
    text = target.read_text(encoding="utf-8", errors="replace")
    if not old or old not in text:
        return {"ok": False, "error": "old_not_found", "path": path}
    if text.count(old) != 1:
        return {"ok": False, "error": "old_not_unique", "n": text.count(old)}
    stack = getattr(rt, "_edit_stack", None)
    if stack is None:
        rt._edit_stack = []
        stack = rt._edit_stack
    stack.append((path, text))
    target.write_text(text.replace(old, new, 1), encoding="utf-8")
    return {"ok": True, "path": path, "replaced": 1}

def rollback(rt: Any) -> Dict[str, Any]:
    ws = _ws(rt)
    stack = getattr(rt, "_edit_stack", None) or []
    if ws is None or not stack:
        return {"ok": False, "error": "nothing_to_rollback"}
    path, text = stack.pop()
    (ws / path).write_text(text, encoding="utf-8")
    return {"ok": True, "path": path, "restored": True}

def rename(rt: Any, src: str, dest: str) -> Dict[str, Any]:
    ws = _ws(rt)
    if ws is None:
        return {"ok": False, "error": "no_workspace"}
    a, b = (ws / src).resolve(), (ws / dest).resolve()
    try:
        a.relative_to(ws.resolve())
        b.relative_to(ws.resolve())
    except ValueError:
        return {"ok": False, "error": "path_escape"}
    if not a.is_file():
        return {"ok": False, "error": "not found"}
    if b.exists():
        return {"ok": False, "error": "dest_exists"}
    b.parent.mkdir(parents=True, exist_ok=True)
    a.replace(b)
    return {"ok": True, "src": src, "dest": dest}

def delete(rt: Any, path: str) -> Dict[str, Any]:
    ws = _ws(rt)
    if ws is None:
        return {"ok": False, "error": "no_workspace"}
    target = (ws / path).resolve()
    try:
        target.relative_to(ws.resolve())
    except ValueError:
        return {"ok": False, "error": "path_escape"}
    if not target.is_file():
        return {"ok": False, "error": "not found"}
    stack = getattr(rt, "_edit_stack", None)
    if stack is None:
        rt._edit_stack = []
        stack = rt._edit_stack
    stack.append((path, target.read_text(encoding="utf-8", errors="replace")))
    target.unlink()
    return {"ok": True, "path": path, "deleted": True}

def dispatch(rt: Any, tool: str, args: Dict[str, Any]) -> Dict[str, Any] | None:
    if tool in {"_retry", "parse_fail"}:
        from core.kernel.parse_fail import parse_fail
        return parse_fail(str((args or {}).get("reason") or "unparseable"))
    if tool == "grep":
        return grep(rt, str((args or {}).get("pattern") or ""), str((args or {}).get("path") or ""))
    if tool == "glob":
        return glob_files(rt, str((args or {}).get("pattern") or "**/*.py"))
    if tool == "apply_patch":
        return apply_patch(rt, str((args or {}).get("path") or ""), str((args or {}).get("old") or ""), str((args or {}).get("new") or ""))
    if tool == "rollback":
        return rollback(rt)
    if tool == "rename":
        return rename(rt, str((args or {}).get("src") or ""), str((args or {}).get("dest") or ""))
    if tool == "delete":
        return delete(rt, str((args or {}).get("path") or ""))
    return None
