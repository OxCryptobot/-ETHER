"""Citrine — Qdrant + Ollama embeddings."""

from __future__ import annotations

import os
from typing import List, Dict, Any
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
    def __init__(
        self,
        qdrant_url: str | None = None,
        ollama_url: str | None = None,
        embed_model: str | None = None,
        collection_name: str = "ether_code",
    ):
        self.client = QdrantClient(
            url=qdrant_url or os.getenv("QDRANT_URL", "http://localhost:6333"),
            check_compatibility=False,
        )
        self.ollama_url = (ollama_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.embed_model = embed_model or os.getenv("ETHER_EMBED_MODEL", "nomic-embed-text")
        self.default_collection = collection_name
        self.http = httpx.Client(timeout=60.0)
        self._ensure_collection(self.default_collection)

    def _ensure_collection(self, name: str) -> None:
        try:
            cols = self.client.get_collections().collections
            if not any(c.name == name for c in cols):
                self.client.create_collection(
                    collection_name=name,
                    vectors_config=qmodels.VectorParams(size=768, distance=qmodels.Distance.COSINE),
                )
        except Exception:
            pass

    def _embed(self, text: str) -> List[float]:
        try:
            resp = self.http.post(
                f"{self.ollama_url}/api/embeddings",
                json={"model": self.embed_model, "prompt": text},
            )
            resp.raise_for_status()
            return resp.json()["embedding"]
        except Exception:
            return [0.0] * 768

    def execute(self, request: Envelope) -> ResponseEnvelope:
        try:
            payload = request.payload if isinstance(request.payload, CitrineRequest) else CitrineRequest(
                **(request.payload.model_dump() if hasattr(request.payload, "model_dump") else {})
            )
            collection = payload.collection or self.default_collection

            if payload.action == "search":
                results = self._search(collection, payload.query or "", payload.top_k)
                out = CitrineResponse(results=results, collection=collection, action="search")
            elif payload.action == "add":
                self._add(collection, payload.documents or [])
                out = CitrineResponse(results=[], collection=collection, action="add")
            else:
                return ResponseEnvelope(
                    task_id=request.task_id,
                    source_gem="citrine",
                    error=GemError(type=GemErrorType.UNKNOWN, message=f"Unsupported action {payload.action}", recoverable=False),
                )

            return ResponseEnvelope(task_id=request.task_id, source_gem="citrine", payload=out)
        except Exception as e:
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="citrine",
                error=GemError(type=GemErrorType.RUNTIME, message=str(e), recoverable=True),
            )

    def _search(self, collection: str, query: str, top_k: int) -> List[RetrievalResult]:
        if not query:
            return []
        try:
            hits = self.client.search(collection_name=collection, query_vector=self._embed(query), limit=top_k)
            return [
                RetrievalResult(
                    id=str(h.id),
                    text=(h.payload or {}).get("text", ""),
                    score=float(h.score),
                    metadata={k: v for k, v in (h.payload or {}).items() if k != "text"},
                )
                for h in hits
            ]
        except Exception:
            return []

    def _add(self, collection: str, documents: List[Dict[str, Any]]) -> None:
        if not documents:
            return
        points = [
            qmodels.PointStruct(
                id=str(uuid4()),
                vector=self._embed(doc.get("text", "")),
                payload={"text": doc.get("text", ""), **doc.get("metadata", {})},
            )
            for doc in documents
        ]
        self.client.upsert(collection_name=collection, points=points)
