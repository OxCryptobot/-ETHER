"""Citrine — Modular memory gem: Qdrant + Ollama embeddings + smart chunking.

Stage 2 (Modular Intelligence): Citrine is a first-class gem, not an optional
side effect. Design rules:

- Verified-only patterns collection (callers must only write sandbox-passed code)
- Zero-vector ban: failed embeds never get stored or queried as if real
- Named collections with explicit purpose
- Lazy Qdrant connect so registry can load even when Qdrant is down; health()
  reports truth for doctor / Control Matrix
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx

from core.schemas import (
    CitrineRequest,
    CitrineResponse,
    Envelope,
    GemError,
    GemErrorType,
    ResponseEnvelope,
    RetrievalResult,
)

# Canonical collections — product surface for Modular Intelligence
COLLECTION_CODE = "ether_code"
COLLECTION_PATTERNS = "patterns"
COLLECTION_FAILURES = "failures"
COLLECTION_RUNS = "runs"
CANONICAL_COLLECTIONS = (
    COLLECTION_CODE,
    COLLECTION_PATTERNS,
    COLLECTION_FAILURES,
    COLLECTION_RUNS,
)

# nomic-embed-text default dim; overridden after first successful embed if needed
DEFAULT_VECTOR_SIZE = 768


class EmbedError(RuntimeError):
    """Embedding failed — must not be papered over with a zero vector."""


class Citrine:
    def __init__(
        self,
        qdrant_url: str | None = None,
        ollama_url: str | None = None,
        embed_model: str | None = None,
        collection_name: str = COLLECTION_CODE,
        *,
        connect: bool = True,
    ):
        self.qdrant_url = (qdrant_url or os.getenv("QDRANT_URL", "http://localhost:6333")).rstrip(
            "/"
        )
        self.ollama_url = (
            ollama_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ).rstrip("/")
        self.embed_model = embed_model or os.getenv("ETHER_EMBED_MODEL", "nomic-embed-text")
        self.default_collection = collection_name
        self.http = httpx.Client(timeout=60.0)
        self._client = None
        self._vector_size = DEFAULT_VECTOR_SIZE
        self._last_error: Optional[str] = None
        if connect:
            self._connect()

    # -- connectivity -------------------------------------------------------

    def _connect(self) -> bool:
        try:
            from qdrant_client import QdrantClient

            self._client = QdrantClient(url=self.qdrant_url, check_compatibility=False)
            # touch API
            _ = self._client.get_collections()
            self._last_error = None
            for name in CANONICAL_COLLECTIONS:
                self._ensure_collection(name)
            return True
        except Exception as e:
            self._client = None
            self._last_error = str(e)[:300]
            return False

    @property
    def client(self):
        if self._client is None:
            self._connect()
        return self._client

    def health(self) -> Dict[str, Any]:
        """Honest status for doctor / infra — never claims healthy on silence."""
        out: Dict[str, Any] = {
            "qdrant_url": self.qdrant_url,
            "embed_model": self.embed_model,
            "reachable": False,
            "embed_ok": False,
            "collections": {},
            "error": self._last_error,
        }
        try:
            c = self.client
            if c is None:
                return out
            cols = {x.name: x for x in c.get_collections().collections}
            out["reachable"] = True
            out["error"] = None
            for name in CANONICAL_COLLECTIONS:
                info = cols.get(name)
                if info is None:
                    out["collections"][name] = {"exists": False, "points": 0}
                else:
                    try:
                        detail = c.get_collection(name)
                        pts = int(getattr(detail, "points_count", 0) or 0)
                    except Exception:
                        pts = None
                    out["collections"][name] = {"exists": True, "points": pts}
            # embed probe (short)
            try:
                vec = self._embed("citrine health probe")
                out["embed_ok"] = any(v != 0.0 for v in vec)
                out["vector_size"] = len(vec)
            except EmbedError as e:
                out["embed_ok"] = False
                out["error"] = str(e)[:200]
        except Exception as e:
            out["reachable"] = False
            out["error"] = str(e)[:300]
        return out

    def _ensure_collection(self, name: str, vector_size: Optional[int] = None) -> None:
        if self._client is None:
            return
        from qdrant_client.http import models as qmodels

        size = int(vector_size or self._vector_size)
        try:
            cols = self._client.get_collections().collections
            if any(c.name == name for c in cols):
                return
            self._client.create_collection(
                collection_name=name,
                vectors_config=qmodels.VectorParams(size=size, distance=qmodels.Distance.COSINE),
            )
        except Exception as e:
            # Collection may race-create; surface only if still missing
            self._last_error = str(e)[:200]

    # -- embeddings ---------------------------------------------------------

    def _embed(self, text: str) -> List[float]:
        """Real embedding or raise. Never return an all-zero poison vector."""
        try:
            resp = self.http.post(
                f"{self.ollama_url}/api/embeddings",
                json={"model": self.embed_model, "prompt": (text or "")[:8000]},
            )
            resp.raise_for_status()
            data = resp.json()
            vec = data.get("embedding") or data.get("embeddings")
            if isinstance(vec, list) and vec and isinstance(vec[0], list):
                vec = vec[0]
            if not isinstance(vec, list) or not vec:
                raise EmbedError(f"empty embedding from {self.embed_model}")
            out = [float(x) for x in vec]
            if not any(v != 0.0 for v in out):
                raise EmbedError(f"all-zero embedding from {self.embed_model}")
            self._vector_size = len(out)
            return out
        except EmbedError:
            raise
        except Exception as e:
            raise EmbedError(f"embed failed ({self.embed_model}): {e}") from e

    # -- gem API ------------------------------------------------------------

    def execute(self, request: Envelope) -> ResponseEnvelope:
        try:
            payload = (
                request.payload
                if isinstance(request.payload, CitrineRequest)
                else CitrineRequest(
                    **(
                        request.payload.model_dump()
                        if hasattr(request.payload, "model_dump")
                        else {}
                    )
                )
            )
            collection = payload.collection or self.default_collection

            if self.client is None:
                return ResponseEnvelope(
                    task_id=request.task_id,
                    source_gem="citrine",
                    error=GemError(
                        type=GemErrorType.DEPENDENCY,
                        message=f"Qdrant unreachable at {self.qdrant_url}: {self._last_error or 'offline'}",
                        recoverable=True,
                        suggested_action="Start Qdrant (docker compose up qdrant) or set QDRANT_URL",
                    ),
                )

            if payload.action == "search":
                results = self._search(collection, payload.query or "", payload.top_k)
                out = CitrineResponse(results=results, collection=collection, action="search")
            elif payload.action == "add":
                n = self._add(collection, payload.documents or [])
                out = CitrineResponse(
                    results=[],
                    collection=collection,
                    action="add",
                    # detail carried via empty results; count in metadata path
                )
                # attach count via a synthetic retrieval row is awkward; ok flag is enough
                _ = n
            elif payload.action == "health":
                h = self.health()
                out = CitrineResponse(
                    results=[
                        RetrievalResult(
                            id="health",
                            text=str(h),
                            score=1.0 if h.get("reachable") else 0.0,
                            metadata=h,
                        )
                    ],
                    collection=collection,
                    action="health",
                )
            else:
                return ResponseEnvelope(
                    task_id=request.task_id,
                    source_gem="citrine",
                    error=GemError(
                        type=GemErrorType.UNKNOWN,
                        message=f"Unsupported action {payload.action}",
                        recoverable=False,
                    ),
                )

            return ResponseEnvelope(task_id=request.task_id, source_gem="citrine", payload=out)
        except EmbedError as e:
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="citrine",
                error=GemError(
                    type=GemErrorType.DEPENDENCY,
                    message=str(e),
                    recoverable=True,
                    suggested_action=f"ollama pull {self.embed_model}",
                ),
            )
        except Exception as e:
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="citrine",
                error=GemError(type=GemErrorType.RUNTIME, message=str(e), recoverable=True),
            )

    def _search(self, collection: str, query: str, top_k: int) -> List[RetrievalResult]:
        if not query or self._client is None:
            return []
        self._ensure_collection(collection)
        hits = self._client.search(
            collection_name=collection,
            query_vector=self._embed(query),
            limit=max(1, int(top_k or 5)),
        )
        return [
            RetrievalResult(
                id=str(h.id),
                text=(h.payload or {}).get("text", ""),
                score=float(h.score),
                metadata={k: v for k, v in (h.payload or {}).items() if k != "text"},
            )
            for h in hits
        ]

    def _add(self, collection: str, documents: List[Dict[str, Any]]) -> int:
        if not documents or self._client is None:
            return 0
        from qdrant_client.http import models as qmodels

        from core.chunking import chunk_python_source

        points = []
        for doc in documents:
            text = doc.get("text", "")
            meta = dict(doc.get("metadata") or {})
            path = str(meta.get("path", ""))
            if path.endswith(".py") or "def " in text or "class " in text:
                pieces = chunk_python_source(text, path=path)
            else:
                pieces = [{"text": text, "metadata": meta}] if text.strip() else []

            for piece in pieces:
                body = piece.get("text") or ""
                if not body.strip():
                    continue
                vec = self._embed(body)
                payload = {"text": body, **meta, **piece.get("metadata", {})}
                points.append(
                    qmodels.PointStruct(
                        id=str(uuid4()),
                        vector=vec,
                        payload=payload,
                    )
                )
        if not points:
            return 0
        self._ensure_collection(collection, vector_size=len(points[0].vector))
        self._client.upsert(collection_name=collection, points=points)
        return len(points)
