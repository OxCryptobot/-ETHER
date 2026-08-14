"""pep8_review must be a first-class ToolRuntime tool for GEMS agents."""
from __future__ import annotations


def test_pep8_review_in_tool_specs():
    from core.tool_runtime import TOOL_SPECS

    names = {t["name"] for t in TOOL_SPECS}
    assert "pep8_review" in names


def test_pep8_review_api_for_gems():
    from core.pep8_reviewer import review_paths

    # GEMS call this path directly when they have filesystem access
    report = review_paths(["core/pep8_reviewer.py"])
    assert hasattr(report, "ok")
    assert hasattr(report, "findings")
