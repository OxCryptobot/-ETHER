"""p2 leftover: bandit credit + amethyst log peeled off Pipeline."""
from __future__ import annotations

import inspect

from core.loop.bandit_credit import credit_attempts, policy_update
from core.loop.log_run import log_run
from core.pipeline import Pipeline


def test_pipeline_credit_delegates() -> None:
    src = inspect.getsource(Pipeline._credit_attempts)
    assert "credit_attempts" in src
    assert "learning_enabled" not in src


def test_pipeline_log_delegates() -> None:
    src = inspect.getsource(Pipeline._log)
    assert "log_run" in src
    assert "AmethystRequest" not in src


def test_named_entries() -> None:
    assert callable(credit_attempts)
    assert callable(policy_update)
    assert callable(log_run)
    assert "final" in inspect.signature(policy_update).parameters
