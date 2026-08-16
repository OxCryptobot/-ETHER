"""Model router dual-lane + strangler style hygiene."""
from __future__ import annotations


def test_select_fast_lane():
    from core.model_router import select_model

    s = select_model("fast")
    assert s["lane"] == "fast"
    assert s["model"]


def test_select_live_lane():
    from core.model_router import select_model

    s = select_model({"class": "live", "id": "job_live_1", "note": "live attempt"})
    assert s["lane"] == "live"


def test_select_scripted_not_live():
    from core.model_router import select_model

    s = select_model({"class": "fast", "note": "scripted hard baseline"})
    assert s["lane"] == "fast"


def test_status_publishes():
    from core.model_router import status

    st = status()
    assert "fast_model" in st
    assert "samples" in st
    assert st["samples"]["live"]["lane"] == "live"


def test_strangler_style_gate():
    from core.strangler_style_gate import check

    out = check()
    assert out["ok"] is True
    assert out["ok_n"] == out["n"]
