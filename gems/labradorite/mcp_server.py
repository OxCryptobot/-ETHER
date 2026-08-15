"""Labradorite MCP server — thin tool surface over critique / review.

Exposes tools:
  - critique_code
  - profile_complexity

All paths go through Labradorite.execute so the same static + heuristic
signals feed Amethyst / memory bus. Honest gate remains upstream.

Usage (stdio):
  python -m gems.labradorite.mcp_server
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional
from uuid import uuid4

try:
    from mcp.server import MCPServer

    _MCP_AVAILABLE = True
except Exception:  # pragma: no cover
    MCPServer = None  # type: ignore[misc, assignment]
    _MCP_AVAILABLE = False


def _lab() -> Any:
    from gems.labradorite.profiler import Labradorite

    return Labradorite()


def _envelope(code: str = "", language: str = "python"):
    from core.schemas import LabradoriteRequest, Envelope

    payload = LabradoriteRequest(code=code or "", language=language)
    return Envelope(
        task_id=uuid4(),
        target_gem="labradorite",
        payload=payload,
        timeout_seconds=30,
    )


def create_server(name: str = "ether-labradorite") -> Any:
    """Build an MCPServer that wraps Labradorite. Raises if mcp SDK missing."""
    if not _MCP_AVAILABLE or MCPServer is None:
        raise RuntimeError(
            "mcp package not installed. Install with: pip install 'mcp[cli]>=1.0' "
            "or uv add 'mcp[cli]'"
        )

    mcp = MCPServer(name)

    @mcp.tool()
    def critique_code(code: str, language: str = "python") -> Dict[str, Any]:
        """Run Labradorite static + heuristic critique on source.

        Returns complexity, severity signals, suggested improvements.
        Same path as the native gem (feeds Amethyst / infinity loop).
        """
        lab = _lab()
        env = _envelope(code=code, language=language)
        res = lab.execute(env)
        if res.error:
            return {
                "ok": False,
                "error": res.error.message,
                "error_type": str(getattr(res.error, "type", "runtime")),
            }
        p = res.payload
        return {
            "ok": True,
            "complexity_score": float(getattr(p, "complexity_score", 0.5) or 0.5),
            "critique": (getattr(p, "critique", "") or "")[:500],
            "suggested_improvements": list(getattr(p, "suggested_improvements", []) or [])[:10],
            "confidence_score": float(getattr(p, "confidence_score", 0.6) or 0.6),
        }

    @mcp.tool()
    def profile_complexity(code: str) -> Dict[str, Any]:
        """Lightweight complexity + flag scan (subset of full critique)."""
        lab = _lab()
        env = _envelope(code=code)
        res = lab.execute(env)
        if res.error:
            return {"ok": False, "error": res.error.message}
        p = res.payload
        return {
            "ok": True,
            "complexity_score": float(getattr(p, "complexity_score", 0.5) or 0.5),
            "n_suggestions": len(getattr(p, "suggested_improvements", []) or []),
            "critique_preview": (getattr(p, "critique", "") or "")[:200],
        }

    return mcp


def main() -> None:
    if not _MCP_AVAILABLE:
        print("mcp SDK not installed", file=sys.stderr)
        sys.exit(2)
    server = create_server()
    server.run()


if __name__ == "__main__":
    main()
