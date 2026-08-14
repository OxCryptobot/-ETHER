"""Smoke tests for embedded PEP8 reviewer."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_review_paths_self():
    from core.pep8_reviewer import format_report_md, review_paths

    report = review_paths([ROOT / "core" / "pep8_reviewer.py"])
    assert report.scope
    assert report.tool in ("ruff", "compile", "none")
    assert isinstance(report.ok, bool)
    md = format_report_md(report)
    assert "PEP 8 Review Summary" in md
    assert "Findings" in md


def test_review_empty_scope():
    from core.pep8_reviewer import review_paths

    report = review_paths([ROOT / "core" / "does_not_exist_xyz"])
    assert report.ok is True
