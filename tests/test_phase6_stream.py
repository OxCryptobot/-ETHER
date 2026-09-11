"""Phase 6 batch: stream outbox + worktree list + LSP client fallback."""
from __future__ import annotations

from core.loop.lsp_client import lsp_hover, lsp_status
from core.loop.stream_obs import stream_observation
from core.loop.worktree import list_worktrees


def test_lsp_client_fail_closed_or_binary() -> None:
    st = lsp_status()
    assert "via" in st
    if not st["ok"]:
        assert st["error"] == "no_lsp_server"
    hv = lsp_hover(__file__, name="test_lsp_client_fail_closed_or_binary")
    assert hv.get("via") == "ast_lite" or hv.get("ok") is False


def test_stream_observation_outbox() -> None:
    out = stream_observation("list_files", {"ok": True, "n": 1}, job_id="p6_stream")
    assert out["ok"] is True
    assert out["lane"] == "outbox"
    assert out["id"].startswith("chat_")


def test_worktree_list() -> None:
    rows = list_worktrees()
    assert "worktrees" in rows
    assert "n" in rows
