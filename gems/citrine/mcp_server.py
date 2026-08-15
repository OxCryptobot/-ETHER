"""Citrine MCP server — thin standardized resource + tool surface over memory.

Exposes:
  Resources (context the host loads):
    - citrine://health
    - citrine://collections
    - citrine://collections/{name}
  Tools (model-invoked actions):
    - search_memory
    - memory_health
    - list_collections

All paths go through Citrine.execute / health so Qdrant + embed behaviour,
zero-vector ban, and lazy connect remain identical.
Training wheels / honest gate remain upstream.

Usage (stdio):
  python -m gems.citrine.mcp_server

Or import create_server() for in-process tests / MCP Client.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Optional
from uuid import uuid4

try:
    from mcp.server import MCPServer

    _MCP_AVAILABLE = True
except Exception:  # pragma: no cover
    MCPServer = None  # type: ignore[misc, assignment]
    _MCP_AVAILABLE = False


def _citrine() -> Any:
    from gems.citrine.memory import Citrine

    return Citrine(connect=True)


def _envelope(action: str = "search", **extra: Any):
    from core.schemas import CitrineRequest, Envelope

    payload = CitrineRequest(
        action=action,  # type: ignore[arg-type]
        **{k: v for k, v in extra.items() if k in ("query", "collection", "top_k", "documents")},
    )
    return Envelope(
        task_id=uuid4(),
        target_gem="citrine",
        payload=payload,
        timeout_seconds=30,
    )


def create_server(name: str = "ether-citrine") -> Any:
    """Build an MCPServer that wraps Citrine. Raises if mcp SDK missing."""
    if not _MCP_AVAILABLE or MCPServer is None:
        raise RuntimeError(
            "mcp package not installed. Install with: pip install 'mcp[cli]>=1.0' "
            "or uv add 'mcp[cli]'"
        )

    mcp = MCPServer(name)

    # ---- Resources (application-controlled context) ----

    @mcp.resource("citrine://health")
    def resource_health() -> str:
        """Honest Citrine + Qdrant + embed readiness as JSON."""
        c = _citrine()
        h = c.health()
        return json.dumps(h, indent=2, default=str)

    @mcp.resource("citrine://collections")
    def resource_collections() -> str:
        """List canonical collections and point counts."""
        c = _citrine()
        h = c.health()
        cols = h.get("collections") or {}
        return json.dumps({"collections": cols, "reachable": h.get("reachable")}, indent=2)

    @mcp.resource("citrine://collections/{name}")
    def resource_collection(name: str) -> str:
        """Detail for one collection (exists + points)."""
        c = _citrine()
        h = c.health()
        cols = h.get("collections") or {}
        info = cols.get(name) or {"exists": False, "points": 0}
        return json.dumps({"name": name, **info, "reachable": h.get("reachable")}, indent=2)

    # ---- Tools (model-controlled actions) ----

    @mcp.tool()
    def search_memory(
        query: str,
        collection: str = "ether_code",
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """Semantic search over a Citrine collection (Qdrant + nomic-embed).

        Returns ranked RetrievalResult rows. Empty list on miss or offline.
        """
        c = _citrine()
        env = _envelope(action="search", query=query, collection=collection, top_k=top_k)
        res = c.execute(env)
        if res.error:
            return {
                "ok": False,
                "error": res.error.message,
                "error_type": str(getattr(res.error, "type", "runtime")),
                "recoverable": bool(getattr(res.error, "recoverable", True)),
                "results": [],
            }
        p = res.payload
        results = []
        for r in getattr(p, "results", []) or []:
            results.append(
                {
                    "id": r.id,
                    "text": (r.text or "")[:2000],
                    "score": float(r.score),
                    "metadata": dict(r.metadata or {}),
                }
            )
        return {
            "ok": True,
            "collection": getattr(p, "collection", collection),
            "action": "search",
            "n": len(results),
            "results": results,
        }

    @mcp.tool()
    def memory_health() -> Dict[str, Any]:
        """Report Qdrant reachability, embed probe, and collection stats."""
        c = _citrine()
        h = c.health()
        return {
            "ok": bool(h.get("reachable")),
            "qdrant_url": h.get("qdrant_url"),
            "embed_model": h.get("embed_model"),
            "reachable": h.get("reachable"),
            "embed_ok": h.get("embed_ok"),
            "collections": h.get("collections") or {},
            "error": h.get("error"),
            "mcp_available": True,
            "note": "Citrine MCP surface is live; honest gate remains upstream",
        }

    @mcp.tool()
    def list_collections() -> Dict[str, Any]:
        """List canonical Citrine collections and point counts."""
        c = _citrine()
        h = c.health()
        return {
            "ok": bool(h.get("reachable")),
            "collections": h.get("collections") or {},
            "canonical": ["ether_code", "patterns", "failures", "runs"],
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
