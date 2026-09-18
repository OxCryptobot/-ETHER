"""Edit transaction: snapshot → patch → tests → promote or revert."""
from __future__ import annotations
import shutil
from pathlib import Path
from typing import Dict, List, Optional

class EditTx:
    def __init__(self, workspace: Path, snapshot: Optional[Path] = None) -> None:
        self.workspace = Path(workspace)
        self.snapshot = Path(snapshot or (self.workspace.parent / (self.workspace.name + ".snap")))
        self.log: List[str] = []

    def begin(self) -> None:
        if self.snapshot.exists():
            shutil.rmtree(self.snapshot, ignore_errors=True)
        shutil.copytree(self.workspace, self.snapshot, dirs_exist_ok=True)
        self.log.append("begin")

    def revert(self) -> None:
        if not self.snapshot.exists():
            return
        shutil.rmtree(self.workspace, ignore_errors=True)
        shutil.copytree(self.snapshot, self.workspace, dirs_exist_ok=True)
        self.log.append("revert")

    def promote(self) -> None:
        if self.snapshot.exists():
            shutil.rmtree(self.snapshot, ignore_errors=True)
        self.log.append("promote")

    def finish(self, tests_ok: bool) -> Dict[str, object]:
        if tests_ok:
            self.promote()
        else:
            self.revert()
        return {"ok": tests_ok, "log": list(self.log)}
