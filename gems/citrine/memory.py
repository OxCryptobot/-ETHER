"""Citrine — local-first memory layer using Qdrant + Ollama embeddings."""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from uuid import uuid4

import httpx
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from core.schemas import (
    Envelope,
    ResponseEnvelope,
    GemError,
    GemErrorType,
    CitrineRequest,
    CitrineResponse,
    RetrievalResult,
)


class Citrine:
    """Hybrid memory gem (vector store + embeddings)."""

    def __init__(
        self,
        qdrant_url: str = "http://localhost:6333",
        ollama_url: str = "http://localhost:11434",
        embed_model: str = "nomic-embed-text",
        collection_name: str = "ether_code",
    ):
        self.client = QdrantClient(url=qdrant_url, check_compatibility=False)
        self.ollama_url = ollama_url.rstrip("/")
        self.embed_model = embed_model
        self.default_collection = collection_name
        self.http = httpx.Client(timeout=60.0)
        self._ensure_collection(self.default_collection)

    def _ensure_collection(self, name: str) -> None:
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == name for c in collections)
            if not exists:
                self.client.create_collection(
                    collection_name=name,
                    vectors_config=qmodels.VectorParams(
                        size=768,
                        distance=qmodels.Distance.COSINE,
                    ),
                )
        except Exception:
            # Qdrant may not be running — fail softly
            pass

    def _embed(self, text: str) -> List[float]:
        """Get embedding from Ollama."""
        try:
            resp = self.http.post(
                f"{self.ollama_url}/api/embeddings",
                json={"model": self.embed_model, "prompt": text},
            )
            resp.raise_for_status()
            return resp.json()["embedding"]
        except Exception:
            # Fallback zero vector if Ollama is unavailable
            return [0.0] * 768

    def execute(self, request: Envelope) -> ResponseEnvelope:
        try:
            if isinstance(request.payload, CitrineRequest):
                payload = request.payload
            else:
                data = request.payload.model_dump() if hasattr(request.payload, "model_dump") else {}
                payload = CitrineRequest(**data)

            collection = payload.collection or self.default_collection

            if payload.action == "search":
                results = self._search(collection, payload.query or "", payload.top_k)
                response_payload = CitrineResponse(
                    results=results,
                    collection=collection,
                    action="search",
                )
            elif payload.action == "add":
                self._add(collection, payload.documents or [])
                response_payload = CitrineResponse(
                    results=[],
                    collection=collection,
                    action="add",
                )
            else:
                return ResponseEnvelope(
                    task_id=request.task_id,
                    source_gem="citrine",
                    error=GemError(
                        type=GemErrorType.UNKNOWN,
                        message=f"Unsupported action: {payload.action}",
                        recoverable=False,
                    ),
                )

            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="citrine",
                payload=response_payload,
            )

        except Exception as e:
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="citrine",
                error=GemError(
                    type=GemErrorType.RUNTIME,
                    message=str(e),
                    recoverable=True,
                ),
            )

    def _search(self, collection: str, query: str, top_k: int) -> List[RetrievalResult]:
        if not query:
            return []

        try:
            vector = self._embed(query)
            hits = self.client.search(
                collection_name=collection,
                query_vector=vector,
                limit=top_k,
            )

            results = []
            for hit in hits:
                results.append(
                    RetrievalResult(
                        id=str(hit.id),
                        text=hit.payload.get("text", "") if hit.payload else "",
                        score=float(hit.score),
                        metadata={k: v for k, v in (hit.payload or {}).items() if k != "text"},
                    )
                )
            return results
        except Exception:
            return []

    def _add(self, collection: str, documents: List[Dict[str, Any]]) -> None:
        if not documents:
            return

        points = []
        for doc in documents:
            text = doc.get("text", "")
            vector = self._embed(text)
            points.append(
                qmodels.PointStruct(
                    id=str(uuid4()),
                    vector=vector,
                    payload={
                        "text": text,
                        **doc.get("metadata", {}),
                    },
                )
            )

        if points:
            self.client.upsert(collection_name=collection, points=points)
