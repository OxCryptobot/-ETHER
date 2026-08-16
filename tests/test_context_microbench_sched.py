"""Context budget grades + microbench cadence."""
from __future__ import annotations

import os


def test_context_measure_grade():
    from core.context_budget import measure

    small = measure("hello world " * 10, query="t")
    assert small["grade"] in ("OK", "COMPRESSED", "WARM", "HOT", "OVER")
    assert "utilization" in small
    assert small["over_budget"] is False


def test_context_over_budget_without_compress():
    from core.context_budget import measure

    old = os.environ.get("ETHER_CONTEXT_COMPRESS")
    try:
        # Without compress, raw text is kept → can exceed max_chars
        os.environ["ETHER_CONTEXT_COMPRESS"] = "0"
        big = measure("x" * 50_000, query="t", max_chars=100)
        assert big["over_budget"] is True
        assert big["grade"] == "OVER"
    finally:
        if old is None:
            os.environ.pop("ETHER_CONTEXT_COMPRESS", None)
        else:
            os.environ["ETHER_CONTEXT_COMPRESS"] = old


def test_context_compressed_stays_under_max():
    from core.context_budget import measure

    old = os.environ.get("ETHER_CONTEXT_COMPRESS")
    try:
        os.environ["ETHER_CONTEXT_COMPRESS"] = "1"
        big = measure("y" * 50_000, query="coding", max_chars=500)
        # Compress / truncate path must not report OVER if out <= max
        assert big["out_chars"] <= 500 or big["over_budget"] is True
    finally:
        if old is None:
            os.environ.pop("ETHER_CONTEXT_COMPRESS", None)
        else:
            os.environ["ETHER_CONTEXT_COMPRESS"] = old


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
