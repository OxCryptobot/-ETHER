"""Context budget grades + microbench cadence."""
from __future__ import annotations


def test_context_measure_grade():
    from core.context_budget import measure

    small = measure("hello world " * 10, query="t")
    assert small["grade"] in ("OK", "COMPRESSED", "WARM", "HOT", "OVER")
    assert "utilization" in small
    assert small["over_budget"] is False


def test_context_over_budget():
    from core.context_budget import measure

    big = measure("x" * 50_000, query="t", max_chars=100)
    assert big["over_budget"] is True
    assert big["grade"] == "OVER"


def test_publish_sample():
    from core.context_budget import publish_sample

    p = publish_sample()
    assert p.get("path")
    assert "grade" in p


def test_microbench_schedule_shape():
    from core.microbench_schedule import should_run

    d = should_run(interval_s=300)
    assert "run" in d
    assert "reason" in d
    assert d["interval_s"] == 300
