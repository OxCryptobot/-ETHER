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


def seal(root: Path, message: str) -> Dict[str, object]:
    """Commit inside edit_ws only. Never `git commit` in the product root."""
    ws = ensure_tree(root)
    subprocess.run(["git", "add", "-A"], cwd=str(ws), capture_output=True, text=True, check=False)
    commit = subprocess.run(
        ["git", "-c", "user.email=ether@local", "-c", "user.name=ether-edit", "commit", "-m", message],
        cwd=str(ws),
        capture_output=True,
        text=True,
        check=False,
    )
    return {"rc": commit.returncode, "tail": (commit.stdout or commit.stderr or "")[-180:]}
