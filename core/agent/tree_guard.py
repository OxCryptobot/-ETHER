"""Batch 9: whole-tree guard for one real-goal attempt (audit W1, W34).

The honest gate judged an attempt by the goal's target test, but the revert restored only
goal['file']. Anything else an attempt changed (a model tool call that edited tests/, a
candidate function that rewrote a test at import time while the gate ran in place) stayed on
disk, so a target could be made to pass by weakening its test.

TreeGuard snapshots the content of every source file before the model is asked (about 1,000
files / 5 MB on the ETHER tree, one read pass), then:

- `violations(allowed)` lists every path that was modified, added or deleted other than the
  goal's own file(s); tests/ is never allowed, even when a goal names it;
- `restore()` puts back ALL touched paths (allowed ones too) and deletes added files.

Runtime state (memory/, artifacts/, caches, the model's edit_ws) is outside the snapshot: the
writer itself updates goal_index, trajectories and lessons during an attempt.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

SKIP_DIRS = frozenset({
    ".git", ".venv", "venv", "env", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "memory", "artifacts", "edit_ws", "sota_ws", "out", "build", "dist", ".qdrant", "models",
})
MAX_FILE_BYTES = 2_000_000
IMMUTABLE_PREFIXES = ("tests/",)


def _walk(root: Path) -> Iterable[Tuple[str, Path]]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for f in filenames:
            if f.endswith((".pyc", ".pyo")):
                continue
            p = Path(dirpath) / f
            yield p.relative_to(root).as_posix(), p


def immutable(rel: str) -> bool:
    rel = (rel or "").replace("\\", "/")
    return any(rel.startswith(p) for p in IMMUTABLE_PREFIXES) or rel.endswith("conftest.py")


class TreeGuard:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.saved: Dict[str, Optional[bytes]] = {}
        self.big: Dict[str, Tuple[int, int]] = {}

    def begin(self) -> "TreeGuard":
        self.saved.clear()
        self.big.clear()
        for rel, p in _walk(self.root):
            try:
                st = p.stat()
                if st.st_size > MAX_FILE_BYTES:
                    self.big[rel] = (st.st_size, st.st_mtime_ns)
                    continue
                self.saved[rel] = p.read_bytes()
            except OSError:
                continue
        return self

    def changed(self) -> Dict[str, str]:
        """{rel: 'modified' | 'added' | 'deleted'} versus the snapshot."""
        out: Dict[str, str] = {}
        now = set()
        for rel, p in _walk(self.root):
            now.add(rel)
            if rel in self.big:
                try:
                    st = p.stat()
                    if (st.st_size, st.st_mtime_ns) != self.big[rel]:
                        out[rel] = "modified"
                except OSError:
                    pass
                continue
            if rel not in self.saved:
                out[rel] = "added"
                continue
            try:
                if p.read_bytes() != self.saved[rel]:
                    out[rel] = "modified"
            except OSError:
                out[rel] = "modified"
        for rel in self.saved:
            if rel not in now:
                out[rel] = "deleted"
        for rel in self.big:
            if rel not in now:
                out[rel] = "deleted"
        return out

    def violations(self, allowed: Iterable[str]) -> List[str]:
        ok = {str(a).replace("\\", "/") for a in allowed if a}
        return sorted(rel for rel in self.changed() if rel not in ok or immutable(rel))

    def restore(self, rels: Optional[Iterable[str]] = None) -> List[str]:
        """Put every touched path (or just `rels`) back. Returns the paths restored."""
        changes = self.changed()
        want = set(changes) if rels is None else {r.replace("\\", "/") for r in rels} & set(changes)
        done: List[str] = []
        for rel in sorted(want):
            p = self.root / rel
            try:
                if changes[rel] == "added":
                    p.unlink(missing_ok=True)
                elif rel in self.saved and self.saved[rel] is not None:
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(self.saved[rel])  # type: ignore[arg-type]
                else:
                    continue  # a >2 MB file: cannot restore content, still reported as a violation
                done.append(rel)
            except OSError:
                continue
        return done
