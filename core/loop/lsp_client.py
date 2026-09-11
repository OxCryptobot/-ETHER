"""LSP client. Real server if on PATH, else AST lite. Never fake pyright."""
from __future__ import annotations

import shutil
from typing import Any, Dict

from core.loop.ast_intel import hover as ast_hover


def which_server() -> str:
    for name in ("pyright-langserver", "pyright", "pylsp"):
        if shutil.which(name):
            return name
    return ""


def lsp_status() -> Dict[str, Any]:
    server = which_server()
    if not server:
        return {"ok": False, "via": "none", "error": "no_lsp_server", "note": "fail-closed"}
    return {"ok": True, "via": server, "error": "", "note": "binary present; no stdio session yet"}


def lsp_hover(path: str, name: str = "", line: int = 0, col: int = 0) -> Dict[str, Any]:
    st = lsp_status()
    if name:
        lite = ast_hover(path, name)
        lite["lsp"] = st
        return lite
    st.update({"path": path, "line": int(line), "col": int(col)})
    return st
