"""Edit transaction: snapshot → patch → tests → promote or revert."""
from __future__ import annotations
import shutil
import stat
from pathlib import Path
from typing import Dict, List, Optional

def _skip_git(directory: str, names: List[str]) -> List[str]:
    return [name for name in names if name in (".git", "__pycache__")]


def _wipe(path: Path) -> None:
    if not path.exists():
        return
    for child in path.rglob("*"):
        try:
            # Add the write bit; never drop read/exec (0o200 on a POSIX dir
            # makes rmtree unable to list it, so the wipe silently failed).
            child.chmod(child.stat().st_mode | stat.S_IWRITE)
        except OSError:
            pass
    shutil.rmtree(path, ignore_errors=True)


class EditTx:
    def __init__(self, workspace: Path, snapshot: Optional[Path] = None) -> None:
        self.workspace = Path(workspace)
        self.snapshot = Path(snapshot or (self.workspace.parent / (self.workspace.name + ".snap")))
        self.log: List[str] = []

    def begin(self) -> None:
        if self.snapshot.exists():
            _wipe(self.snapshot)
        shutil.copytree(self.workspace, self.snapshot, dirs_exist_ok=True, ignore=_skip_git)
        self.log.append("begin")

    def revert(self) -> None:
        if not self.snapshot.exists():
            return
        for child in list(self.workspace.iterdir()):
            if child.name == ".git":
                continue
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
        for child in self.snapshot.iterdir():
            if child.name == ".git":
                continue
            dest = self.workspace / child.name
            if child.is_dir():
                shutil.copytree(child, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(child, dest)
        self.log.append("revert")

    def promote(self) -> None:
        if self.snapshot.exists():
            _wipe(self.snapshot)
        self.log.append("promote")

    def finish(self, tests_ok: bool) -> Dict[str, object]:
        if tests_ok:
            self.promote()
        else:
            self.revert()
        return {"ok": tests_ok, "log": list(self.log)}


class FileTx:
    """All-or-nothing edit of a few named files (batch 5, multi-target goals).

    EditTx copies the whole workspace, which is far too heavy per attempt on the 1650.
    FileTx snapshots only the paths it is given (content, or "absent" for a file the
    edit creates) and restores every one of them on revert: a two-file fix whose second
    half fails leaves neither file changed, and a new file is removed again."""

    def __init__(self, root: Path, rels: List[str]) -> None:
        self.root = Path(root)
        self.rels = [r.replace("\\", "/") for r in dict.fromkeys(rels)]
        self.saved: Dict[str, Optional[bytes]] = {}
        self.log: List[str] = []
        self.created_dirs: List[Path] = []

    def begin(self) -> "FileTx":
        for rel in self.rels:
            p = self.root / rel
            self.saved[rel] = p.read_bytes() if p.is_file() else None
            if not p.parent.exists():
                d = p.parent
                while not d.exists() and d != self.root:
                    self.created_dirs.append(d)
                    d = d.parent
        self.log.append("begin")
        return self

    def revert(self) -> None:
        for rel, data in self.saved.items():
            p = self.root / rel
            try:
                if data is None:
                    p.unlink(missing_ok=True)
                else:
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(data)
            except OSError:
                pass
        for d in sorted(self.created_dirs, key=lambda x: -len(str(x))):
            try:
                if d.is_dir() and not any(d.iterdir()):
                    d.rmdir()
            except OSError:
                pass
        self.log.append("revert")

    def commit(self) -> None:
        self.saved.clear()
        self.log.append("commit")

    def changed(self) -> List[str]:
        out = []
        for rel, data in self.saved.items():
            p = self.root / rel
            now = p.read_bytes() if p.is_file() else None
            if now != data:
                out.append(rel)
        return out
