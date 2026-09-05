"""LSP client. Fail-closed until a real language server is configured."""
from __future__ import annotations

from typing import Any, Dict


def lsp_status() -> Dict[str, Any]:
    return {
        "ok": False,
        "via": "none",
        "error": "no_lsp_server",
        "note": "fail-closed",
    }


def lsp_hover(path: str, line: int = 0, col: int = 0) -> Dict[str, Any]:
    st = lsp_status()
    st.update({"path": path, "line": int(line), "col": int(col)})
    return st
