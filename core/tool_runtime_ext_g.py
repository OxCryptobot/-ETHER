"""Phase G tool extensions mixin implementation."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

EXTRA_SPECS = (
    {"name": "grep", "doc": "Search files for a regex. args: pattern, path (optional)."},
    {"name": "glob", "doc": "List files matching a glob. args: pattern (e.g. '**/*.py')."},
    {"name": "apply_patch", "doc": "Surgical exact-match edit. args: path, old, new. Fail-closed."},
    {"name": "rollback", "doc": "Undo last write_file/apply_patch. No args."},
    {
        "name": "pep8_review",
        "doc": "PEP8/ruff style review. args: path (optional, default '.').",
    },
    {
        "name": "edit_lines",
        "doc": "Replace a 1-indexed inclusive line span. args: path, start_line, end_line, new.",
    },
    {
        "name": "bug_comments",
        "doc": "Extract BUG/FIXME/XXX comments from workspace source (not tests).",
    },
)


class ToolExtMixin:
    workspace: Optional[Path]
    _undo: List[Tuple[str, Optional[str]]]

    def _ensure_undo(self) -> None:
        if not hasattr(self, "_undo") or self._undo is None:
            self._undo = []

    def _resolve_path(self, path: str):
        from core.tool_runtime import _blocked

        assert self.workspace is not None
        reason = _blocked(path)
        if reason:
            return None, reason
        target = (self.workspace / path).resolve()
        try:
            target.relative_to(self.workspace.resolve())
        except ValueError:
            return None, "path escape refused"
        return target, None

    def _push_undo(self, path: str, target: Path) -> None:
        self._ensure_undo()
        if target.is_file():
            prev = target.read_text(encoding="utf-8", errors="replace")
        else:
            prev = None
        self._undo.append((path.replace("\\", "/"), prev))

    def _obs_apply_patch(self, path: str, old: str, new: str) -> Dict[str, Any]:
        target, err = self._resolve_path(path)
        if err:
            return {"ok": False, "error": err}
        assert target is not None
        if not target.is_file():
            return {"ok": False, "error": f"not found: {path}"}
        if not old:
            return {"ok": False, "error": "old must be non-empty"}
        body = target.read_text(encoding="utf-8", errors="replace")
        count = body.count(old)
        if count == 0:
            return {"ok": False, "error": "old not found (exact match required)"}
        if count > 1:
            return {"ok": False, "error": f"old matched {count} times; must be unique"}
        self._push_undo(path, target)
        target.write_text(body.replace(old, new, 1), encoding="utf-8")
        return {"ok": True, "path": path, "replaced": 1, "mutated": True}

    def _obs_edit_lines(self, path: str, start_line: Any, end_line: Any, new: str) -> Dict[str, Any]:
        from core.hard_live_tools import edit_lines
        from core.tool_runtime import _ast_reject_py

        target, err = self._resolve_path(path)
        if err:
            return {"ok": False, "error": err}
        assert target is not None
        if not target.is_file():
            return {"ok": False, "error": f"not found: {path}"}
        try:
            s = int(start_line)
            e = int(end_line)
        except (TypeError, ValueError):
            return {"ok": False, "error": "start_line and end_line must be integers"}
        body = target.read_text(encoding="utf-8", errors="replace")
        try:
            updated = edit_lines(body, s, e, new if new is not None else "")
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        ast_err = _ast_reject_py(path, updated)
        if ast_err:
            return {"ok": False, "error": ast_err}
        self._push_undo(path, target)
        target.write_text(updated, encoding="utf-8")
        return {"ok": True, "path": path, "start_line": s, "end_line": e, "mutated": True, "n_chars": len(updated)}

    def _obs_bug_comments(self, path: str = ".") -> Dict[str, Any]:
        from core.hard_live_tools import extract_bug_comments

        assert self.workspace is not None
        root = self.workspace
        rel = (path or ".").strip() or "."
        if rel not in (".", ""):
            target, err = self._resolve_path(rel)
            if err:
                return {"ok": False, "error": err}
            assert target is not None
            root = target if target.is_dir() else target.parent
        hits = extract_bug_comments(root)
        return {"ok": True, "hits": hits, "n": len(hits)}

    def _obs_rollback(self) -> Dict[str, Any]:
        self._ensure_undo()
        if not self._undo:
            return {"ok": False, "error": "nothing to rollback"}
        path, prev = self._undo.pop()
        target, err = self._resolve_path(path)
        if err:
            return {"ok": False, "error": err}
        assert target is not None
        if prev is None:
            if target.is_file():
                target.unlink()
            return {"ok": True, "path": path, "action": "deleted_created_file"}
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(prev, encoding="utf-8")
        return {"ok": True, "path": path, "action": "restored"}

    def _obs_grep(self, pattern: str, path: str = ".") -> Dict[str, Any]:
        from core.tool_runtime import _blocked

        assert self.workspace is not None
        if not pattern:
            return {"ok": False, "error": "pattern required"}
        try:
            rx = re.compile(pattern)
        except re.error as e:
            return {"ok": False, "error": f"bad regex: {e}"}
        root_path = (path or ".").strip() or "."
        if root_path in (".", ""):
            search_root = self.workspace
        else:
            target, err = self._resolve_path(root_path)
            if err:
                return {"ok": False, "error": err}
            search_root = target
        hits: List[Dict[str, Any]] = []
        if search_root is None:
            return {"ok": False, "error": "not found"}
        if search_root.is_file():
            files = [search_root]
        elif search_root.is_dir():
            files = [p for p in sorted(search_root.rglob("*")) if p.is_file()]
        else:
            return {"ok": False, "error": f"not found: {root_path}"}
        for fp in files:
            if "__pycache__" in fp.parts:
                continue
            rel = str(fp.relative_to(self.workspace)).replace("\\", "/")
            if _blocked(rel):
                continue
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    hits.append({"path": rel, "line": i, "text": line[:200]})
                    if len(hits) >= 40:
                        return {"ok": True, "hits": hits, "n": len(hits), "truncated": True}
        return {"ok": True, "hits": hits, "n": len(hits), "truncated": False}

    def _obs_glob(self, pattern: str) -> Dict[str, Any]:
        from core.tool_runtime import _blocked

        assert self.workspace is not None
        pat = (pattern or "").strip()
        if not pat:
            return {"ok": False, "error": "pattern required"}
        if pat.startswith("/") or ".." in Path(pat).parts:
            return {"ok": False, "error": "path escape refused"}
        matches = []
        for fp in sorted(self.workspace.glob(pat)):
            if not fp.is_file() or "__pycache__" in fp.parts:
                continue
            rel = str(fp.relative_to(self.workspace)).replace("\\", "/")
            if _blocked(rel):
                continue
            matches.append(rel)
            if len(matches) >= 80:
                break
        return {"ok": True, "files": matches, "n": len(matches)}

    def _obs_pep8_review(self, path: str = ".") -> Dict[str, Any]:
        assert self.workspace is not None
        rel = (path or ".").strip() or "."
        if rel in (".", ""):
            target = self.workspace
        else:
            target, err = self._resolve_path(rel)
            if err:
                return {"ok": False, "error": err}
            assert target is not None
        try:
            from core.pep8_reviewer import review_paths

            report = review_paths([target])
        except Exception as e:
            return {"ok": False, "error": f"pep8_review: {type(e).__name__}: {e}"[:200]}
        top = [{"path": f.path, "line": f.line, "code": f.code, "severity": f.severity, "message": f.message[:160]} for f in report.findings[:15]]
        return {"ok": bool(report.ok), "tool": report.tool, "assessment": report.assessment, "n_critical": report.n_critical, "n_warning": report.n_warning, "n_suggestion": report.n_suggestion, "findings": top, "next_actions": list(report.next_actions)[:5], "path": rel}
