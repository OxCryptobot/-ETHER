"""AST transactional edits — Package 1C + Phase 2.2 multi-file.

Python-first. Snapshot every target file before mutation. On verification
failure, restore the exact prior bytes. This is the shared safety layer for
tool_runtime, Clear Quartz, multifile, and any future write path.

Design rules (locked):
- Never write without a live snapshot.
- AST parse is a hard gate for .py files (reject syntax-broken writes).
- Verification is caller-supplied (pytest, repo-oracle, custom).
- Rollback is atomic per transaction: all-or-nothing restore.
- No network, no subprocesses inside this module.
"""
from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

ROOT = Path(__file__).resolve().parents[1]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


@dataclass
class FileSnapshot:
    path: Path
    existed: bool
    content: Optional[bytes]
    sha: str


@dataclass
class EditResult:
    ok: bool
    committed: bool = False
    rolled_back: bool = False
    written: List[str] = field(default_factory=list)
    error: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)


class EditTransaction:
    """Context-manager transactional editor for one or more source files."""

    def __init__(
        self,
        root: Union[str, Path] = ROOT,
        *,
        allow_outside_root: bool = False,
        require_ast: bool = True,
    ) -> None:
        self.root = Path(root).resolve()
        self.allow_outside_root = allow_outside_root
        self.require_ast = require_ast
        self._snapshots: Dict[Path, FileSnapshot] = {}
        self._pending: Dict[Path, bytes] = {}
        self._closed = False
        self._committed = False

    def __enter__(self) -> "EditTransaction":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self._committed and not self._closed:
            self.rollback()
        self._closed = True

    def _resolve(self, rel: Union[str, Path]) -> Path:
        p = Path(rel)
        if p.is_absolute():
            target = p.resolve()
        else:
            target = (self.root / p).resolve()
        if not self.allow_outside_root:
            try:
                target.relative_to(self.root)
            except ValueError as e:
                raise ValueError(f"path escapes root: {rel}") from e
        if ".." in Path(rel).parts:
            raise ValueError(f"path escape via ..: {rel}")
        return target

    def _snapshot(self, path: Path) -> None:
        if path in self._snapshots:
            return
        if path.is_file():
            data = path.read_bytes()
            self._snapshots[path] = FileSnapshot(
                path=path,
                existed=True,
                content=data,
                sha=_sha256(data),
            )
        else:
            self._snapshots[path] = FileSnapshot(
                path=path,
                existed=False,
                content=None,
                sha="",
            )

    def write(self, rel: Union[str, Path], content: str, *, encoding: str = "utf-8") -> None:
        if self._closed:
            raise RuntimeError("transaction already closed")
        path = self._resolve(rel)
        data = content.encode(encoding)

        if self.require_ast and path.suffix == ".py":
            try:
                ast.parse(content)
            except SyntaxError as e:
                raise ValueError(
                    f"AST reject for {rel}: {e.msg} (line {e.lineno})"
                ) from e

        self._snapshot(path)
        self._pending[path] = data

    def apply_many(self, files: Dict[str, str], *, encoding: str = "utf-8") -> None:
        """Stage many relative path -> content writes. All AST-gated before any apply."""
        if self._closed:
            raise RuntimeError("transaction already closed")
        # Parse-all first so a late syntax error does not leave partial staging intent
        for rel, content in (files or {}).items():
            path = self._resolve(rel)
            if self.require_ast and path.suffix == ".py":
                try:
                    ast.parse(content if content is not None else "")
                except SyntaxError as e:
                    raise ValueError(
                        f"AST reject for {rel}: {e.msg} (line {e.lineno})"
                    ) from e
        for rel, content in (files or {}).items():
            self.write(rel, content if content is not None else "", encoding=encoding)

    def write_bytes(self, rel: Union[str, Path], data: bytes) -> None:
        if self._closed:
            raise RuntimeError("transaction already closed")
        path = self._resolve(rel)
        if self.require_ast and path.suffix == ".py":
            try:
                ast.parse(data.decode("utf-8"))
            except (SyntaxError, UnicodeDecodeError) as e:
                raise ValueError(f"AST/encoding reject for {rel}: {e}") from e
        self._snapshot(path)
        self._pending[path] = data

    def _apply_pending(self) -> List[str]:
        written: List[str] = []
        for path, data in self._pending.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            try:
                written.append(str(path.relative_to(self.root)))
            except ValueError:
                written.append(str(path))
        return written

    def rollback(self) -> None:
        for path, snap in self._snapshots.items():
            try:
                if snap.existed:
                    if snap.content is not None:
                        path.write_bytes(snap.content)
                else:
                    if path.exists():
                        path.unlink()
            except OSError:
                pass
        self._pending.clear()
        self._closed = True

    def commit(self) -> EditResult:
        if self._closed:
            return EditResult(ok=False, error="transaction closed")
        written = self._apply_pending()
        self._committed = True
        self._closed = True
        self._pending.clear()
        return EditResult(ok=True, committed=True, written=written)

    def verify_and_commit(
        self,
        verify: Callable[[], bool],
        *,
        on_fail_rollback: bool = True,
    ) -> EditResult:
        if self._closed:
            return EditResult(ok=False, error="transaction closed")

        written = self._apply_pending()
        ok = False
        err = ""
        try:
            ok = bool(verify())
        except Exception as e:
            ok = False
            err = f"{type(e).__name__}: {e}"

        if ok:
            self._committed = True
            self._closed = True
            self._pending.clear()
            return EditResult(ok=True, committed=True, written=written)

        if on_fail_rollback:
            self.rollback()
            return EditResult(
                ok=False,
                rolled_back=True,
                written=written,
                error=err or "verify returned False",
                detail={"snapshots": len(self._snapshots)},
            )

        self._closed = True
        return EditResult(
            ok=False,
            committed=False,
            written=written,
            error=err or "verify returned False (no rollback)",
        )

    @property
    def pending_paths(self) -> List[str]:
        out = []
        for p in self._pending:
            try:
                out.append(str(p.relative_to(self.root)))
            except ValueError:
                out.append(str(p))
        return out

    @property
    def snapshot_count(self) -> int:
        return len(self._snapshots)


def transactional_write(
    path: Union[str, Path],
    content: str,
    verify: Callable[[], bool],
    *,
    root: Union[str, Path] = ROOT,
) -> EditResult:
    with EditTransaction(root) as tx:
        tx.write(path, content)
        return tx.verify_and_commit(verify)


def transactional_write_many(
    files: Dict[str, str],
    verify: Callable[[], bool],
    *,
    root: Union[str, Path] = ROOT,
) -> EditResult:
    """Multi-file atomic write under AST gate + verify."""
    with EditTransaction(root) as tx:
        tx.apply_many(files)
        return tx.verify_and_commit(verify)
