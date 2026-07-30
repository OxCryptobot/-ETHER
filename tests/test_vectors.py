"""Contract tests for core.vectors — the typed-edge envelope (A-3/A-4)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.vectors import Provenance, Vector, prompt_hash


def _vector(**overrides) -> Vector:
    kwargs = dict(
        trace_id=uuid4(),
        seq=0,
        loop="L1",
        from_vertex="runner",
        to_vertex="selenite",
        edge_kind="plan",
        payload_type="SeleniteRequest",
    )
    kwargs.update(overrides)
    return Vector(**kwargs)


def test_extra_fields_rejected():
    with pytest.raises(ValidationError):
        _vector(bogus_field=1)


def test_provenance_extra_fields_rejected():
    with pytest.raises(ValidationError):
        Provenance(temperature=0.2)


def test_defaults():
    v = _vector()
    assert v.schema_version == 1
    assert v.payload == {}
    assert v.degraded == []
    assert v.confidence == 0.0
    assert v.verification_score is None
    assert v.duration_ms == 0.0
    assert v.created_at
    assert v.provenance.model is None


def test_prompt_hash_stability_and_length():
    h1 = prompt_hash("write hello")
    h2 = prompt_hash("write hello")
    assert h1 == h2
    assert len(h1) == 16
    assert prompt_hash("write hello!") != h1
    assert all(c in "0123456789abcdef" for c in h1)


def test_uuid_trace_round_trip():
    tid = uuid4()
    v = _vector(trace_id=tid, seq=3)
    dumped = v.model_dump()
    v2 = Vector.model_validate(dumped)
    assert v2.trace_id == tid
    assert v2.vector_id == v.vector_id
    assert v2.seq == 3


def test_schema_version_literal_enforced():
    with pytest.raises(ValidationError):
        _vector(schema_version=2)


def test_illegal_vertex_rejected():
    with pytest.raises(ValidationError):
        _vector(from_vertex="qdrant")


def test_degraded_lists_independent_per_instance():
    v1 = _vector()
    v2 = _vector()
    v1.degraded.append("citrine_unavailable:ImportError")
    assert v2.degraded == []


def test_payload_lists_independent_per_instance():
    v1 = _vector()
    v2 = _vector()
    v1.payload["k"] = 1
    assert v2.payload == {}
