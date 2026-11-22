"""A passing edit stays in its own git tree. That tree is not the product repo."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict


def tree_path(root: Path) -> Path:
    return Path(root) / "edit_ws"


def ensure_tree(root: Path) -> Path:
    ws = tree_path(root)
    ws.mkdir(parents=True, exist_ok=True)
    if not (ws / ".git").is_dir():
        subprocess.run(["git", "init"], cwd=str(ws), capture_output=True, text=True, check=False)
    return ws


def seal(root: Path, message: str, paths: list[str] | None = None) -> Dict[str, object]:
    """Commit inside edit_ws only. A task may not delete a file it does not own."""
    ws = ensure_tree(root)
    if paths:
        owned = {p.replace("\\", "/") for p in paths}
        listed = subprocess.run(["git", "ls-files"], cwd=str(ws), capture_output=True, text=True, check=False)
        for rel in (listed.stdout or "").splitlines():
            rel = rel.strip().replace("\\", "/")
            if not rel or rel in owned:
                continue
            if not (ws / rel).exists():
                subprocess.run(["git", "checkout", "--", rel], cwd=str(ws), capture_output=True, text=True, check=False)
        subprocess.run(["git", "add", "--", *paths], cwd=str(ws), capture_output=True, text=True, check=False)
    else:
        subprocess.run(["git", "add", "-A"], cwd=str(ws), capture_output=True, text=True, check=False)
    commit = subprocess.run(
        ["git", "-c", "user.email=ether@local", "-c", "user.name=ether-edit", "commit", "-m", message],
        cwd=str(ws),
        capture_output=True,
        text=True,
        check=False,
    )
    return {"rc": commit.returncode, "tail": (commit.stdout or commit.stderr or "")[-180:]}
