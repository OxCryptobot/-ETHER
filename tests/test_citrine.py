"""Regression tests for Citrine memory.

These use a REAL Qdrant (no mocks) because the bug they cover was invisible to
mocks: `_add` upserted into a collection that was never created, Qdrant 404'd,
and the error was swallowed so the pipeline only ever reported `citrine=False`.
A mocked client would have happily accepted the write.

They skip (rather than fail) when Qdrant is unreachable so the suite still runs
on a box without it — a skip is honest, a false green is not.
"""

from __future__ import annotations

import os
from uuid import uuid4

import httpx
import pytest

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")


def _qdrant_up() -> bool:
    try:
        return httpx.get(f"{QDRANT_URL}/healthz", timeout=2.0).status_code == 200
    except Exception:
        return False


requires_qdrant = pytest.mark.skipif(
    not _qdrant_up(), reason=f"Qdrant not reachable at {QDRANT_URL}"
)


@pytest.fixture
def citrine():
    from gems.citrine.memory import Citrine

    return Citrine()


@requires_qdrant
def test_add_creates_missing_collection(citrine):
    """The actual bug: writing to a non-default collection 404'd forever.

    `_ensure_collection` ran only in __init__ and only for the default
    collection, but core/patterns.py writes to 'patterns'.
    """
    collection = f"test_regress_{uuid4().hex[:8]}"
    try:
        citrine._add(collection, [{"text": "def add(a, b):\n    return a + b"}])
        names = {c.name for c in citrine.client.get_collections().collections}
        assert collection in names, "add() must create the collection it writes to"
        info = citrine.client.get_collection(collection)
        assert info.points_count > 0, "points must actually persist"
    finally:
        try:
            citrine.client.delete_collection(collection)
        except Exception:
            pass


@requires_qdrant
def test_index_pass_pattern_reports_success(citrine):
    """End-to-end guard on the path the pipeline actually uses.

    Previously returned {'ok': False, 'error': "Collection `patterns` doesn't
    exist!"} on every single run, which surfaced only as `citrine=False`.
    """
    from core.patterns import index_pass_pattern

    res = index_pass_pattern(
        objective="regression: store a pass pattern",
        code="def is_even(n):\n    return n % 2 == 0",
        confidence=1.0,
        strategy="test",
    )
    assert res.get("ok") is True, f"pattern indexing failed: {res.get('error')}"


@requires_qdrant
def test_embed_returns_real_vector(citrine):
    """A zero vector is Citrine's silent-failure sentinel.

    `_embed` returns [0.0]*768 when embedding fails, which is stored as if it
    were a real embedding and poisons retrieval. If the embed model is missing
    this test tells us loudly instead of silently degrading RAG quality.
    """
    vec = citrine._embed("def is_even(n):\n    return n % 2 == 0")
    assert len(vec) == 768, "nomic-embed-text is expected to yield 768 dims"
    assert any(v != 0.0 for v in vec), (
        "all-zero embedding means the embed call failed silently — "
        f"check that {citrine.embed_model!r} is pulled in Ollama"
    )


def test_citrine_is_registered():
    """build_default_registry() swallows gem import errors.

    test_registry.py deliberately omits citrine from its required set, so a
    completely dead memory gem kept the suite green. This asserts it directly.
    """
    from core.registry import build_default_registry

    assert "citrine" in build_default_registry().list_gems(), (
        "citrine failed to register — its import error was swallowed by "
        "build_default_registry(); check qdrant-client is installed"
    )
