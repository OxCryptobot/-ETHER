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
            child.chmod(stat.S_IWRITE)
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
