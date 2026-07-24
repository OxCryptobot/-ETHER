"""Citrine — local-first memory layer using Qdrant."""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from uuid import uuid4

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from core.schemas import (
    Envelope,
    ResponseEnvelope,
    GemError,
    GemErrorType,
)
from pydantic import BaseModel, Field


# Temporary local schemas until we expand core/schemas.py
class CitrineRequest(BaseModel):
    action: str = "search"  # "search" | "add" | "delete"
    query: Optional[str] = None
    collection: str = "code"
    top_k: int = 5
    documents: Optional[List[Dict[str, Any]]] = None  # for "add"
    filters: Dict[str, Any] = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    id: str
    text: str
    score: float
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CitrineResponse(BaseModel):
    results: List[RetrievalResult] = Field(default_factory=list)
    collection: str
    action: str


class Citrine:
    """Hybrid memory gem (vector + future graph)."""

    def __init__(
        self,
        qdrant_url: str = "http://localhost:6333",
        collection_name: str = "ether_code",
    ):
        self.client = QdrantClient(url=qdrant_url)
        self.default_collection = collection_name
        self._ensure_collection(self.default_collection)

    def _ensure_collection(self, name: str) -> None:
        collections = self.client.get_collections().collections
        exists = any(c.name == name for c in collections)
        if not exists:
            self.client.create_collection(
                collection_name=name,
                vectors_config=qmodels.VectorParams(
                    size=768,  # nomic-embed-text / bge size
                    distance=qmodels.Distance.COSINE,
                ),
            )

    def execute(self, request: Envelope) -> ResponseEnvelope:
        # For now we accept a raw dict payload until we fully expand schemas
        try:
            payload_data = request.payload
            if hasattr(payload_data, "model_dump"):
                data = payload_data.model_dump()
            else:
                data = payload_data if isinstance(payload_data, dict) else {}

            action = data.get("action", "search")
            collection = data.get("collection", self.default_collection)

            if action == "search":
                query = data.get("query", "")
                top_k = data.get("top_k", 5)
                results = self._search(collection, query, top_k)
                response_payload = CitrineResponse(
                    results=results,
                    collection=collection,
                    action="search",
                )
            elif action == "add":
                documents = data.get("documents", [])
                self._add(collection, documents)
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
                        message=f"Unsupported action: {action}",
                        recoverable=False,
                    ),
                )

            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="citrine",
                payload=response_payload,  # type: ignore[arg-type]
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
        # Placeholder: real embedding will be added with an embed model
        # For now we return empty results so the interface is ready
        return []

    def _add(self, collection: str, documents: List[Dict[str, Any]]) -> None:
        if not documents:
            return

        points = []
        for doc in documents:
            points.append(
                qmodels.PointStruct(
                    id=str(uuid4()),
                    vector=[0.0] * 768,  # placeholder zero vector
                    payload={
                        "text": doc.get("text", ""),
                        **doc.get("metadata", {}),
                    },
                )
            )

        self.client.upsert(collection_name=collection, points=points)
