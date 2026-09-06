"""p2 leftover: fail_run + retrieve peeled off Pipeline."""
from __future__ import annotations

import inspect

from core.loop.fail_run import fail_run
from core.loop.retrieve import fetch_context, fetch_repo_map, needs_repo_context
from core.pipeline import Pipeline


def test_pipeline_fail_delegates() -> None:
    src = inspect.getsource(Pipeline._fail)
    assert "fail_run" in src
    assert "maybe_propose_fabricate" not in src


def test_pipeline_retrieve_delegates() -> None:
    assert "fetch_repo_map" in inspect.getsource(Pipeline._fetch_repo_map)
    assert "fetch_context" in inspect.getsource(Pipeline._fetch_context)
    assert callable(fail_run)
    assert callable(fetch_repo_map)
    assert callable(fetch_context)


def test_needs_repo_context() -> None:
    assert needs_repo_context("refactor this repo") is True
    assert needs_repo_context("add two numbers") is False
    assert Pipeline()._needs_repo_context("fix the bug in core/loop") is True
